"""Execution of RDNA 2 SDWA (0xF9), DPP16 (0xFA), and DPP8 (0xE9/0xEA) forms
for VOP1, VOP2, and VOPC instructions in the reference interpreter (#21).

Semantics follow AMD's public RDNA 2 ISA specification (sections 6.5 SDWA and 6.6 DPP).
"""
from emu.rdna2_exec_ops import VECTOR, VECTOR_COMPARE, bits_float, float_bits
from emu.rdna2_operands_ext import BOUND_CTRL_BIT, CLAMP_BIT, DPP8, DPP8_FI, DPP16, FI_BIT, OMOD_SHIFT, SDWA

MASK32 = 0xFFFF_FFFF
EXT_CODES = frozenset({SDWA, DPP16, DPP8, DPP8_FI})
# (shift, width_bits) for BYTE_0..3, WORD_0..1, DWORD
_SEL_INFO = ((0, 8), (8, 8), (16, 8), (24, 8), (0, 16), (16, 16), (0, 32))
_OMOD_SCALE = {1: 2.0, 2: 4.0, 3: 0.5}


def is_ext(family, src0):
    return family in ("VOP1", "VOP2", "VOPC") and src0 in EXT_CODES


def _operand_float_flags(name):
    """Return (src_is_f32, dst_is_f32) from the instruction's operand types."""
    if name.startswith("v_cvt_"):            # v_cvt_[mode_]<destination>_<source>
        parts = name.split("_")
        return parts[-1] == "f32", parts[-2] == "f32"
    if name == "v_frexp_exp_i32_f32":
        return True, False
    is_f32 = name.endswith("_f32")
    return is_f32, is_f32


def _extract_sel(val, sel, sext):
    if sel >= len(_SEL_INFO):
        return val & MASK32
    shift, width = _SEL_INFO[sel]
    mask = (1 << width) - 1
    out = (val >> shift) & mask
    if sext and width < 32 and (out & (1 << (width - 1))):
        out |= MASK32 ^ mask
    return out & MASK32


def _apply_float_mods(val, absolute, neg):
    if absolute:
        val &= 0x7FFF_FFFF
    if neg:
        val ^= 0x8000_0000
    return val & MASK32


def _apply_omod_clamp(val, omod, clamp):
    if not omod and not clamp:
        return val & MASK32
    f = bits_float(val)
    if omod in _OMOD_SCALE:
        f *= _OMOD_SCALE[omod]
    if clamp:
        f = 0.0 if f != f else min(1.0, max(0.0, f))
    return float_bits(f)


def _place_dst(val, old_dst, dst_sel, dst_unused):
    if dst_sel >= 6:  # DWORD
        return val & MASK32
    shift, width = _SEL_INFO[dst_sel]
    field_mask = (1 << width) - 1
    bits = val & field_mask
    placed = (bits << shift) & MASK32
    if dst_unused == 2:  # UNUSED_PRESERVE
        return (old_dst & ~(field_mask << shift) | placed) & MASK32
    if dst_unused == 1 and (bits & (1 << (width - 1))):  # UNUSED_SEXT
        top_shift = shift + width
        if top_shift < 32:
            placed |= (MASK32 << top_shift) & MASK32
    return placed


def _dpp16_source_lane(lane, ctrl):
    """Return (src_lane, in_bounds) for gfx10 dpp_ctrl."""
    row_base = lane & ~15
    r = lane & 15
    if ctrl <= 0xFF:
        quad_base = lane & ~3
        sel = (ctrl >> (2 * (lane & 3))) & 3
        return quad_base | sel, True
    if 0x101 <= ctrl <= 0x10F:
        n = ctrl & 0xF
        return (row_base + r + n, True) if r + n < 16 else (lane, False)
    if 0x111 <= ctrl <= 0x11F:
        n = ctrl & 0xF
        return (row_base + r - n, True) if r >= n else (lane, False)
    if 0x121 <= ctrl <= 0x12F:
        n = ctrl & 0xF
        return row_base + ((r + n) & 15), True
    if ctrl == 0x140:
        return row_base + (15 - r), True
    if ctrl == 0x141:
        return row_base + (r ^ 7), True
    if 0x150 <= ctrl <= 0x15F:
        return row_base + (ctrl & 0xF), True
    if 0x160 <= ctrl <= 0x16F:
        return row_base + (r ^ (ctrl & 0xF)), True
    return None, False


def _exec_sdwa(wave, family, name, fields, ext):
    from emu.rdna2_exec import Untranslated

    src_is_float, dst_is_float = _operand_float_flags(name)
    s0_code = ext & 0xFF
    s0_scalar = (ext >> 23) & 1
    s0_sel, s0_sext, s0_neg, s0_abs = (ext >> 16) & 7, (ext >> 19) & 1, (ext >> 20) & 1, (ext >> 21) & 1
    s1_code = fields.get("vsrc1", 0)
    s1_scalar = (ext >> 31) & 1
    s1_sel, s1_sext, s1_neg, s1_abs = (ext >> 24) & 7, (ext >> 27) & 1, (ext >> 28) & 1, (ext >> 29) & 1

    def read_src(code, is_scalar, sel, sext, neg, absolute, lane):
        raw = wave.read_scalar(code, None) if is_scalar else wave.v[code][lane]
        val = _extract_sel(raw, sel, 0 if src_is_float else sext)
        return _apply_float_mods(val, absolute, neg) if src_is_float else val

    if family == "VOPC":
        test, writes_exec = VECTOR_COMPARE[name]
        mask = 0
        for lane in wave.active():
            a = read_src(s0_code, s0_scalar, s0_sel, s0_sext, s0_neg, s0_abs, lane)
            b = read_src(s1_code, s1_scalar, s1_sel, s1_sext, s1_neg, s1_abs, lane)
            if test(a, b):
                mask |= 1 << lane
        if writes_exec:
            wave.s[126] = mask
        elif (ext >> 15) & 1:
            wave.write_scalar((ext >> 8) & 0x7F, mask)
        else:
            wave.s[106] = mask
        return

    operation = VECTOR[name]
    dst_sel = (ext >> 8) & 7
    dst_unused = (ext >> 11) & 3
    clamp = (ext >> CLAMP_BIT) & 1
    omod = (ext >> OMOD_SHIFT) & 3
    if not dst_is_float and clamp:
        raise Untranslated(f"SDWA clamp non pris en charge sur opération entière : {name}")
    destination = wave.v[fields["vdst"]]
    for lane in wave.active():
        a = read_src(s0_code, s0_scalar, s0_sel, s0_sext, s0_neg, s0_abs, lane)
        b = read_src(s1_code, s1_scalar, s1_sel, s1_sext, s1_neg, s1_abs, lane) if "vsrc1" in fields else 0
        res = operation(a, b, destination[lane], None, wave.vcc >> lane & 1) & MASK32
        if dst_is_float:
            res = _apply_omod_clamp(res, omod, clamp)
        destination[lane] = _place_dst(res, destination[lane], dst_sel, dst_unused)


def _exec_dpp16(wave, name, fields, ext):
    from emu.rdna2_exec import Untranslated

    ctrl = (ext >> 8) & 0x1FF
    if _dpp16_source_lane(0, ctrl)[0] is None:
        raise Untranslated(f"dpp_ctrl réservé : 0x{ctrl:X}")
    src_is_float, _ = _operand_float_flags(name)
    src0_reg = ext & 0xFF
    src0_snap = list(wave.v[src0_reg])
    src1_snap = list(wave.v[fields["vsrc1"]]) if "vsrc1" in fields else None
    fi = (ext >> FI_BIT) & 1
    bound_ctrl = (ext >> BOUND_CTRL_BIT) & 1
    s0_neg, s0_abs = (ext >> 20) & 1, (ext >> 21) & 1
    s1_neg, s1_abs = (ext >> 22) & 1, (ext >> 23) & 1
    bank_mask = (ext >> 24) & 0xF
    row_mask = (ext >> 28) & 0xF
    operation = VECTOR[name]
    destination = wave.v[fields["vdst"]]
    exec_mask = wave.exec
    for lane in wave.active():
        if not ((row_mask >> (lane >> 4)) & 1) or not ((bank_mask >> ((lane & 15) >> 2)) & 1):
            continue
        src_lane, in_bounds = _dpp16_source_lane(lane, ctrl)
        valid = in_bounds and (fi or bool((exec_mask >> src_lane) & 1))
        if not valid and not bound_ctrl:
            continue
        a = src0_snap[src_lane] if valid else 0
        b = src1_snap[lane] if src1_snap is not None else 0
        if src_is_float:
            a = _apply_float_mods(a, s0_abs, s0_neg)
            b = _apply_float_mods(b, s1_abs, s1_neg)
        destination[lane] = operation(a, b, destination[lane], None, wave.vcc >> lane & 1) & MASK32


def _exec_dpp8(wave, name, fields, ext, fi):
    src0_reg = ext & 0xFF
    src0_snap = list(wave.v[src0_reg])
    src1_snap = list(wave.v[fields["vsrc1"]]) if "vsrc1" in fields else None
    sels = [(ext >> (8 + 3 * i)) & 7 for i in range(8)]
    operation = VECTOR[name]
    destination = wave.v[fields["vdst"]]
    exec_mask = wave.exec
    for lane in wave.active():
        src_lane = (lane & ~7) | sels[lane & 7]
        if not fi and not ((exec_mask >> src_lane) & 1):
            continue
        a = src0_snap[src_lane]
        b = src1_snap[lane] if src1_snap is not None else 0
        destination[lane] = operation(a, b, destination[lane], None, wave.vcc >> lane & 1) & MASK32


def execute(wave, family, name, fields, ext):
    """Execute a VOP1/VOP2/VOPC instruction with SDWA, DPP16, or DPP8 extension word."""
    from emu.rdna2_exec import Untranslated

    kind = fields["src0"]
    if kind == SDWA:
        _exec_sdwa(wave, family, name, fields, ext)
    elif kind == DPP16:
        if family == "VOPC":
            raise Untranslated(f"VOPC non pris en charge en DPP16 : {name}")
        _exec_dpp16(wave, name, fields, ext)
    else:
        if family == "VOPC":
            raise Untranslated(f"VOPC non pris en charge en DPP8 : {name}")
        _exec_dpp8(wave, name, fields, ext, fi=(kind == DPP8_FI))
