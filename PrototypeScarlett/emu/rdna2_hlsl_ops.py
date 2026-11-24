"""Traduction RDNA 2 → HLSL, instruction par instruction (utilisé par emu/rdna2_hlsl.py).

Chaque ligne du wave32 devient un thread d'un groupe de 32. Registres : `s[128]` (SGPR, VCC
en s[106], EXEC en s[126]), `v[n]` (VGPR du thread), `scc`. Les instructions vectorielles ne
s'appliquent que si le bit de la ligne est posé dans EXEC (`active`). Les masques (v_cmp)
sont construits pour tout le groupe par Ballot() ; la sémantique suit l'interpréteur de
référence emu/rdna2_exec*, contre lequel la traduction est vérifiée.
"""
import re

from emu.rdna2_exec_ops import float_bits, signed

NULL, VCC, EXEC, OFF = 125, 106, 126, 0x7D
INLINE_FLOATS = {240: 0.5, 241: -0.5, 242: 1.0, 243: -1.0, 244: 2.0, 245: -2.0, 246: 4.0, 247: -4.0,
                 248: 0.15915494309189535}


class Untranslatable(NotImplementedError):
    """Instruction que le recompilateur ne sait pas encore traduire en HLSL."""


HELPERS = """uint MulHiU32(uint a, uint b) {
  uint a0 = a & 0xFFFFu, a1 = a >> 16, b0 = b & 0xFFFFu, b1 = b >> 16;
  uint p00 = a0 * b0, p01 = a0 * b1, p10 = a1 * b0, p11 = a1 * b1;
  uint mid = (p00 >> 16) + (p01 & 0xFFFFu) + (p10 & 0xFFFFu);
  return p11 + (p01 >> 16) + (p10 >> 16) + (mid >> 16);
}
uint MulHiI32(uint a, uint b) {
  return MulHiU32(a, b) - (asint(a) < 0 ? b : 0u) - (asint(b) < 0 ? a : 0u);
}
uint BfeI32(uint v, uint off, uint w) {
  w &= 31u;
  if (w == 0u) return 0u;
  uint field = (v >> (off & 31u)) & ((1u << w) - 1u);
  uint shift = 32u - w;
  return asuint((asint(field) << shift) >> shift);
}
uint SatF32ToI32(uint a) {
  float x = asfloat(a);
  if ((a & 0x7FFFFFFFu) > 0x7F800000u) return 0u;          // NaN : test sur les bits, pas x != x
  if (x >= 2147483648.0f) return 0x7FFFFFFFu;
  if (x <= -2147483648.0f) return 0x80000000u;
  return asuint((int)x);
}
uint SatF32ToU32(uint a) {
  float x = asfloat(a);
  if ((a & 0x7FFFFFFFu) > 0x7F800000u || x <= 0.0f) return 0u;
  return x >= 4294967296.0f ? 0xFFFFFFFFu : (uint)x;
}
uint FloorToI32(uint a, bool nearest) {
  // v_cvt_flr/rpi_i32_f32 (mesures RDNA 2, VIctory #605) : NaN selon le signe ; rpi = floor(x + 0.5)
  // exact, obtenu en comparant la fraction x - floor(x) (exacte en simple précision) à 0.5.
  if ((a & 0x7FFFFFFFu) > 0x7F800000u) return (a >> 31) != 0u ? 0x80000000u : 0x7FFFFFFFu;
  float x = asfloat(a), f = floor(x);
  if (nearest && x - f >= 0.5f) f += 1.0f;
  return SatF32ToI32(asuint(f));
}
uint SBfeU32(uint v, uint c) {
  uint w = (c >> 16) & 0x7Fu;
  if (w == 0u) return 0u;
  uint field = v >> (c & 31u);
  return w >= 32u ? field : field & ((1u << w) - 1u);
}
uint SBfeI32(uint v, uint c) {
  uint w = (c >> 16) & 0x7Fu;
  if (w == 0u) return 0u;
  int field = asint(v) >> (c & 31u);
  if (w >= 32u) return asuint(field);
  uint shift = 32u - w;
  return asuint((field << shift) >> shift);
}
uint WqmB32(uint v) {
  uint r = 0u;
  [unroll] for (uint q = 0u; q < 32u; q += 4u) { if (((v >> q) & 0xFu) != 0u) r |= 0xFu << q; }
  return r;
}
uint QuadMaskB32(uint v) {
  uint r = 0u;
  [unroll] for (uint q = 0u; q < 8u; ++q) { if (((v >> (q * 4u)) & 0xFu) != 0u) r |= 1u << q; }
  return r;
}
uint LeadingSignsI32(uint v) {
  uint x = (v & 0x80000000u) != 0u ? ~v : v;
  return x == 0u ? 0xFFFFFFFFu : 31u - firstbithigh(x);
}
uint FrexpExpF32(uint a) {
  uint e = (a >> 23) & 0xFFu, m = a & 0x7FFFFFu;
  if (e == 0xFFu || (e == 0u && m == 0u)) return 0u;
  return e != 0u ? e - 126u : asuint((int)firstbithigh(m) - 148);
}
uint FrexpMantF32(uint a) {
  uint e = (a >> 23) & 0xFFu, m = a & 0x7FFFFFu;
  if (e == 0xFFu || (e == 0u && m == 0u)) return a;
  if (e == 0u) m = (m << (23u - firstbithigh(m))) & 0x7FFFFFu;
  return (a & 0x80000000u) | (126u << 23) | m;
}
bool IsNanF32(uint a) {
  return (a & 0x7FFFFFFFu) > 0x7F800000u;
}
uint ClassF32(uint a) {
  uint e = (a >> 23) & 0xFFu, m = a & 0x7FFFFFu, n = a >> 31;
  if (e == 0xFFu) return m != 0u ? ((m >> 22) & 1u) : (n != 0u ? 2u : 9u);
  if (e == 0u) return m == 0u ? (n != 0u ? 5u : 6u) : (n != 0u ? 4u : 7u);
  return n != 0u ? 3u : 8u;
}
uint SadU8(uint a, uint b) {
  uint r = 0u;
  [unroll] for (uint i = 0u; i < 32u; i += 8u) {
    uint x = (a >> i) & 0xFFu, y = (b >> i) & 0xFFu;
    r += x > y ? x - y : y - x;
  }
  return r;
}
uint LerpU8(uint a, uint b, uint c) {
  uint r = 0u;
  [unroll] for (uint i = 0u; i < 32u; i += 8u)
    r |= ((((a >> i) & 0xFFu) + ((b >> i) & 0xFFu) + ((c >> i) & 1u)) >> 1) << i;
  return r;
}
float4 Cube(uint a, uint b, uint c) {
  float x = asfloat(a), y = asfloat(b), z = asfloat(c);
  if (abs(z) >= abs(x) && abs(z) >= abs(y)) return float4(z < 0.0f ? 5.0f : 4.0f, z < 0.0f ? -x : x, -y, 2.0f * z);
  if (abs(y) >= abs(x)) return float4(y < 0.0f ? 3.0f : 2.0f, x, y < 0.0f ? -z : z, 2.0f * y);
  return float4(x < 0.0f ? 1.0f : 0.0f, x < 0.0f ? z : -z, -y, 2.0f * x);
}
uint AlignBit(uint hi, uint lo, uint s) {
  s &= 31u;
  return s == 0u ? lo : ((hi << (32u - s)) | (lo >> s));
}
uint SadU32(uint a, uint b, uint c) {
  return (a > b ? (a - b) : (b - a)) + c;
}
uint MulLegacyF32(uint a, uint b) {
  float x = asfloat(a), y = asfloat(b);
  return (x == 0.0f || y == 0.0f) ? 0u : asuint(x * y);
}
uint FmaLegacyF32(uint a, uint b, uint c) {
  float x = asfloat(a), y = asfloat(b);
  return (x == 0.0f || y == 0.0f) ? c : asuint(mad(x, y, asfloat(c)));
}
uint PermB32(uint a, uint b, uint c) {
  uint r = 0u;
  [unroll] for (uint i = 0u; i < 4u; ++i) {
    uint sel = (c >> (i * 8u)) & 0xFFu;
    uint bt = 0xFFu;
    if (sel < 4u) bt = (b >> (sel * 8u)) & 0xFFu;
    else if (sel < 8u) bt = (a >> ((sel - 4u) * 8u)) & 0xFFu;
    else if (sel == 8u) bt = (b & 0x00008000u) != 0u ? 0xFFu : 0u;
    else if (sel == 9u) bt = (b & 0x80000000u) != 0u ? 0xFFu : 0u;
    else if (sel == 10u) bt = (a & 0x00008000u) != 0u ? 0xFFu : 0u;
    else if (sel == 11u) bt = (a & 0x80000000u) != 0u ? 0xFFu : 0u;
    else if (sel == 12u) bt = 0u;
    r |= bt << (i * 8u);
  }
  return r;
}
"""


def hexa(value):
    return f"0x{value & 0xFFFF_FFFF:X}u"


def source(code, literal=None):
    """Expression HLSL (uint) d'un opérande source 9 bits."""
    if code >= 256:
        return f"v[{code - 256}]"
    if code == NULL:
        return "0u"
    if code < 128:
        return f"s[{code}]"
    if 128 <= code <= 192:
        return f"{code - 128}u"
    if 193 <= code <= 208:
        return hexa(192 - code)
    if code in INLINE_FLOATS:
        return hexa(float_bits(INLINE_FLOATS[code]))
    if code == 255 and literal is not None:
        return hexa(literal)
    raise Untranslatable(f"opérande {code} non traduit")


def source_high(code):
    """Mot haut (uint) d'une source 64 bits : registre suivant, ou extension d'une constante entière."""
    if code >= 256:
        return f"v[{code - 255}]"
    if code < 128 and code != NULL:
        return f"s[{code + 1}]"
    if code == NULL or 128 <= code <= 192:
        return "0u"
    if 193 <= code <= 208:
        return "0xFFFFFFFFu"
    raise Untranslatable(f"opérande 64 bits {code} non traduit")


def scalar_target(code):
    return "s_null" if code == NULL else f"s[{code}]"


def f(expression):
    return f"asfloat({expression})"


# --- Scalaires : modèles avec {d} (destination), {a}, {b} (sources), {k} (immédiat) ----------
SCALAR = {
    "s_mov_b32": "{d} = {a};",
    "s_cmov_b32": "if (scc) {d} = {a};",
    "s_movk_i32": "{d} = {k};",
    "s_cmovk_i32": "if (scc) {d} = {k};",
    "s_addk_i32": "{{ uint x = {d}, y = {k}; uint r = x + y; scc = ((~(x ^ y) & (x ^ r)) >> 31) != 0; {d} = r; }}",
    "s_mulk_i32": "{d} = {d} * {k};",
    "s_cselect_b32": "{d} = scc ? {a} : {b};",
    "s_add_u32": "{{ uint x = {a}, y = {b}; uint r = x + y; scc = r < x; {d} = r; }}",
    "s_sub_u32": "{{ uint x = {a}, y = {b}; scc = x < y; {d} = x - y; }}",
    "s_addc_u32": "{{ uint x = {a}, y = {b}, k = scc ? 1u : 0u; uint r = x + y + k; scc = (r < x) || (k != 0u && r == x); {d} = r; }}",
    "s_subb_u32": "{{ uint x = {a}, y = {b}, k = scc ? 1u : 0u; scc = (x < y) || (k != 0u && x == y); {d} = x - y - k; }}",
    "s_add_i32": "{{ uint x = {a}, y = {b}; uint r = x + y; scc = ((~(x ^ y) & (x ^ r)) >> 31) != 0; {d} = r; }}",
    "s_sub_i32": "{{ uint x = {a}, y = {b}; uint r = x - y; scc = (((x ^ y) & (x ^ r)) >> 31) != 0; {d} = r; }}",
    "s_mul_i32": "{d} = {a} * {b};",
    "s_and_b32": "{{ uint r = {a} & {b}; scc = r != 0; {d} = r; }}",
    "s_or_b32": "{{ uint r = {a} | {b}; scc = r != 0; {d} = r; }}",
    "s_xor_b32": "{{ uint r = {a} ^ {b}; scc = r != 0; {d} = r; }}",
    "s_andn2_b32": "{{ uint r = {a} & ~{b}; scc = r != 0; {d} = r; }}",
    "s_orn2_b32": "{{ uint r = {a} | ~{b}; scc = r != 0; {d} = r; }}",
    "s_nand_b32": "{{ uint r = ~({a} & {b}); scc = r != 0; {d} = r; }}",
    "s_nor_b32": "{{ uint r = ~({a} | {b}); scc = r != 0; {d} = r; }}",
    "s_xnor_b32": "{{ uint r = ~({a} ^ {b}); scc = r != 0; {d} = r; }}",
    "s_lshl_b32": "{{ uint r = {a} << ({b} & 31u); scc = r != 0; {d} = r; }}",
    "s_lshr_b32": "{{ uint r = {a} >> ({b} & 31u); scc = r != 0; {d} = r; }}",
    "s_ashr_i32": "{{ uint r = asuint(asint({a}) >> ({b} & 31u)); scc = r != 0; {d} = r; }}",
    "s_bfm_b32": "{d} = ((1u << ({a} & 31u)) - 1u) << ({b} & 31u);",
    "s_min_u32": "{{ uint x = {a}, y = {b}; scc = x < y; {d} = min(x, y); }}",
    "s_max_u32": "{{ uint x = {a}, y = {b}; scc = x > y; {d} = max(x, y); }}",
    "s_min_i32": "{{ int x = asint({a}), y = asint({b}); scc = x < y; {d} = asuint(min(x, y)); }}",
    "s_max_i32": "{{ int x = asint({a}), y = asint({b}); scc = x > y; {d} = asuint(max(x, y)); }}",
    "s_not_b32": "{{ uint r = ~{a}; scc = r != 0; {d} = r; }}",
    "s_brev_b32": "{d} = reversebits({a});",
    "s_bcnt1_i32_b32": "{{ uint x = {a}; scc = x != 0u; {d} = countbits(x); }}",
    "s_ff1_i32_b32": "{d} = firstbitlow({a});",
    "s_flbit_i32_b32": "{{ uint x = {a}; {d} = x != 0u ? (31u - firstbithigh(x)) : 0xFFFFFFFFu; }}",
    "s_sext_i32_i8": "{d} = asuint((asint({a}) << 24) >> 24);",
    "s_sext_i32_i16": "{d} = asuint((asint({a}) << 16) >> 16);",
    "s_abs_i32": "{{ int x = asint({a}); scc = x != 0; {d} = asuint(x < 0 ? -x : x); }}",
    "s_bitcmp0_b32": "scc = (({a} >> ({b} & 31u)) & 1u) == 0u;",
    "s_bitcmp1_b32": "scc = (({a} >> ({b} & 31u)) & 1u) != 0u;",
    "s_bfe_u32": "{{ uint r = SBfeU32({a}, {b}); scc = r != 0u; {d} = r; }}",
    "s_bfe_i32": "{{ uint r = SBfeI32({a}, {b}); scc = r != 0u; {d} = r; }}",
    "s_absdiff_i32": "{{ uint x = {a} - {b}; uint r = asint(x) < 0 ? 0u - x : x; scc = r != 0u; {d} = r; }}",
    "s_mul_hi_u32": "{d} = MulHiU32({a}, {b});",
    "s_mul_hi_i32": "{d} = MulHiI32({a}, {b});",
    "s_bcnt0_i32_b32": "{{ uint r = 32u - countbits({a}); scc = r != 0u; {d} = r; }}",
    "s_ff0_i32_b32": "{d} = firstbitlow(~{a});",
    "s_flbit_i32": "{d} = LeadingSignsI32({a});",
    "s_wqm_b32": "{{ uint r = WqmB32({a}); scc = r != 0u; {d} = r; }}",
    "s_quadmask_b32": "{{ uint r = QuadMaskB32({a}); scc = r != 0u; {d} = r; }}",
    "s_bitset0_b32": "{d} = {d} & ~(1u << ({a} & 31u));",
    "s_bitset1_b32": "{d} = {d} | (1u << ({a} & 31u));",
}
# (S0 << n) + S1 : SCC = retenue au-delà de 32 bits, bits sortis par le décalage compris.
for _n in range(1, 5):
    SCALAR[f"s_lshl{_n}_add_u32"] = (f"{{{{ uint x = {{a}}, t = x << {_n}u; uint r = t + {{b}}; "
                                     f"scc = (x >> {32 - _n}u) != 0u || r < t; {{d}} = r; }}}}")
# EXEC = combinaison de S0 et d'EXEC ; D = ancien EXEC (saveexec) ou nouveau (wrexec).
EXEC_COMBINE = {"and": "{a} & e", "or": "{a} | e", "xor": "{a} ^ e", "andn2": "{a} & ~e", "orn2": "{a} | ~e",
                "nand": "~({a} & e)", "nor": "~({a} | e)", "xnor": "~({a} ^ e)", "andn1": "~{a} & e",
                "orn1": "~{a} | e"}
for _op, _combine in EXEC_COMBINE.items():
    SCALAR[f"s_{_op}_saveexec_b32"] = f"{{{{ uint e = s[126]; s[126] = {_combine}; scc = s[126] != 0; {{d}} = e; }}}}"
for _op in ("andn1", "andn2"):
    SCALAR[f"s_{_op}_wrexec_b32"] = (f"{{{{ uint e = s[126]; s[126] = {EXEC_COMBINE[_op]}; scc = s[126] != 0; "
                                     f"{{d}} = s[126]; }}}}")
for _name in ("s_nop", "s_waitcnt", "s_waitcnt_vscnt", "s_waitcnt_vmcnt", "s_waitcnt_expcnt",
              "s_waitcnt_lgkmcnt", "s_barrier", "s_sleep", "s_setprio", "s_ttracedata",
              "s_dcache_inv", "s_gl1_inv", "buffer_gl0_inv", "buffer_gl1_inv", "s_clause",
              "s_inst_prefetch"):
    SCALAR[_name] = ""
COMPARE_OPERATORS = {"eq": "==", "lg": "!=", "ne": "!=", "neq": "!=", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}
for _op, _symbol in COMPARE_OPERATORS.items():
    SCALAR[f"s_cmp_{_op}_u32"] = f"scc = {{a}} {_symbol} {{b}};"
    SCALAR[f"s_cmp_{_op}_i32"] = f"scc = asint({{a}}) {_symbol} asint({{b}});"
    SCALAR[f"s_cmpk_{_op}_u32"] = f"scc = {{d}} {_symbol} {{u}};"
    SCALAR[f"s_cmpk_{_op}_i32"] = f"scc = asint({{d}}) {_symbol} asint({{k}});"

BRANCHES = {
    "s_branch": "true", "s_cbranch_scc0": "!scc", "s_cbranch_scc1": "scc",
    "s_cbranch_vccz": "s[106] == 0", "s_cbranch_vccnz": "s[106] != 0",
    "s_cbranch_execz": "s[126] == 0", "s_cbranch_execnz": "s[126] != 0",
}


def scalar_statement(name, fields, literal):
    template = SCALAR[name]
    if not template:
        return ""
    values = {"d": scalar_target(fields.get("sdst", NULL))}
    for key, field in (("a", "ssrc0"), ("b", "ssrc1")):
        if field in fields:
            values[key] = source(fields[field], literal)
    if "simm16" in fields:
        values["k"] = hexa(signed(fields["simm16"], 16))
        values["u"] = hexa(fields["simm16"])
    return template.format(**values)


# --- Vectorielles : expressions uint de {a}, {b}, {c} (sources) et {d} (destination) --------
VECTOR = {
    "v_mov_b32": "{a}",
    "v_add_f32": "asuint(asfloat({a}) + asfloat({b}))",
    "v_sub_f32": "asuint(asfloat({a}) - asfloat({b}))",
    "v_subrev_f32": "asuint(asfloat({b}) - asfloat({a}))",
    "v_mul_f32": "asuint(asfloat({a}) * asfloat({b}))",
    "v_mul_legacy_f32": "MulLegacyF32({a}, {b})",
    "v_min_f32": "asuint(min(asfloat({a}), asfloat({b})))",
    "v_max_f32": "asuint(max(asfloat({a}), asfloat({b})))",
    "v_fmac_f32": "asuint(mad(asfloat({a}), asfloat({b}), asfloat({d})))",
    "v_mac_f32": "asuint(mad(asfloat({a}), asfloat({b}), asfloat({d})))",
    "v_fma_f32": "asuint(mad(asfloat({a}), asfloat({b}), asfloat({c})))",
    "v_mad_f32": "asuint(mad(asfloat({a}), asfloat({b}), asfloat({c})))",
    "v_fma_legacy_f32": "FmaLegacyF32({a}, {b}, {c})",
    "v_fmamk_f32": "asuint(mad(asfloat({a}), asfloat({k}), asfloat({b})))",
    "v_fmaak_f32": "asuint(mad(asfloat({a}), asfloat({b}), asfloat({k})))",
    "v_rcp_f32": "asuint(rcp(asfloat({a})))",
    "v_rsq_f32": "asuint(rsqrt(asfloat({a})))",
    "v_sqrt_f32": "asuint(sqrt(asfloat({a})))",
    "v_exp_f32": "asuint(exp2(asfloat({a})))",
    "v_log_f32": "asuint(log2(asfloat({a})))",
    "v_sin_f32": "asuint(sin(asfloat({a}) * 6.283185307179586f))",
    "v_cos_f32": "asuint(cos(asfloat({a}) * 6.283185307179586f))",
    "v_floor_f32": "asuint(floor(asfloat({a})))",
    "v_ceil_f32": "asuint(ceil(asfloat({a})))",
    "v_trunc_f32": "asuint(trunc(asfloat({a})))",
    "v_rndne_f32": "asuint(round(asfloat({a})))",
    "v_fract_f32": "asuint(frac(asfloat({a})))",
    "v_ldexp_f32": "asuint(ldexp(asfloat({a}), (float)asint({b})))",
    "v_cvt_f32_u32": "asuint((float){a})",
    "v_cvt_f32_i32": "asuint((float)asint({a}))",
    "v_cvt_u32_f32": "SatF32ToU32({a})",
    "v_cvt_i32_f32": "SatF32ToI32({a})",
    "v_cvt_f32_ubyte0": "asuint((float)({a} & 0xFFu))",
    "v_cvt_f32_ubyte1": "asuint((float)(({a} >> 8) & 0xFFu))",
    "v_cvt_f32_ubyte2": "asuint((float)(({a} >> 16) & 0xFFu))",
    "v_cvt_f32_ubyte3": "asuint((float)(({a} >> 24) & 0xFFu))",
    "v_add_nc_u32": "({a} + {b})",
    "v_sub_nc_u32": "({a} - {b})",
    "v_subrev_nc_u32": "({b} - {a})",
    "v_and_b32": "({a} & {b})",
    "v_or_b32": "({a} | {b})",
    "v_xor_b32": "({a} ^ {b})",
    "v_xnor_b32": "(~({a} ^ {b}))",
    "v_not_b32": "(~{a})",
    "v_bfrev_b32": "reversebits({a})",
    "v_ffbl_b32": "firstbitlow({a})",
    "v_ffbh_u32": "({a} != 0u ? (31u - firstbithigh({a})) : 0xFFFFFFFFu)",
    "v_lshlrev_b32": "({b} << ({a} & 31u))",
    "v_lshrrev_b32": "({b} >> ({a} & 31u))",
    "v_ashrrev_i32": "asuint(asint({b}) >> ({a} & 31u))",
    "v_min_u32": "min({a}, {b})",
    "v_max_u32": "max({a}, {b})",
    "v_min_i32": "asuint(min(asint({a}), asint({b})))",
    "v_max_i32": "asuint(max(asint({a}), asint({b})))",
    "v_mul_u32_u24": "(({a} & 0xFFFFFFu) * ({b} & 0xFFFFFFu))",
    "v_mul_hi_u32_u24": "MulHiU32({a} & 0xFFFFFFu, {b} & 0xFFFFFFu)",
    "v_mul_i32_i24": "asuint(((asint({a}) << 8) >> 8) * ((asint({b}) << 8) >> 8))",
    "v_mul_lo_u32": "({a} * {b})",
    "v_mul_hi_u32": "MulHiU32({a}, {b})",
    "v_mul_hi_i32": "MulHiI32({a}, {b})",
    "v_mad_u32_u24": "(({a} & 0xFFFFFFu) * ({b} & 0xFFFFFFu) + {c})",
    "v_mad_i32_i24": "asuint(((asint({a}) << 8) >> 8) * ((asint({b}) << 8) >> 8) + asint({c}))",
    "v_bfe_u32": "(({a} >> ({b} & 31u)) & ((1u << ({c} & 31u)) - 1u))",
    "v_bfe_i32": "BfeI32({a}, {b}, {c})",
    "v_bfi_b32": "(({a} & {b}) | (~{a} & {c}))",
    "v_bfm_b32": "(((1u << ({a} & 31u)) - 1u) << ({b} & 31u))",
    "v_alignbit_b32": "AlignBit({a}, {b}, {c})",
    "v_alignbyte_b32": "AlignBit({a}, {b}, ({c} & 3u) * 8u)",
    "v_perm_b32": "PermB32({a}, {b}, {c})",
    "v_add3_u32": "({a} + {b} + {c})",
    "v_lshl_add_u32": "(({a} << ({b} & 31u)) + {c})",
    "v_add_lshl_u32": "(({a} + {b}) << ({c} & 31u))",
    "v_lshl_or_b32": "(({a} << ({b} & 31u)) | {c})",
    "v_and_or_b32": "(({a} & {b}) | {c})",
    "v_or3_b32": "({a} | {b} | {c})",
    "v_xor3_b32": "({a} ^ {b} ^ {c})",
    "v_xad_u32": "(({a} ^ {b}) + {c})",
    "v_sad_u32": "SadU32({a}, {b}, {c})",
    "v_min3_f32": "asuint(min(min(asfloat({a}), asfloat({b})), asfloat({c})))",
    "v_max3_f32": "asuint(max(max(asfloat({a}), asfloat({b})), asfloat({c})))",
    "v_med3_f32": "asuint(max(min(asfloat({a}), asfloat({b})), min(max(asfloat({a}), asfloat({b})), asfloat({c}))))",
    "v_min3_u32": "min(min({a}, {b}), {c})",
    "v_max3_u32": "max(max({a}, {b}), {c})",
    "v_med3_u32": "max(min({a}, {b}), min(max({a}, {b}), {c}))",
    "v_min3_i32": "asuint(min(min(asint({a}), asint({b})), asint({c})))",
    "v_max3_i32": "asuint(max(max(asint({a}), asint({b})), asint({c})))",
    "v_med3_i32": "asuint(max(min(asint({a}), asint({b})), min(max(asint({a}), asint({b})), asint({c}))))",
    "v_bcnt_u32_b32": "(countbits({a}) + {b})",
    "v_mbcnt_lo_u32_b32": "(countbits({a} & ((1u << lane) - 1u)) + {b})",
    "v_mbcnt_hi_u32_b32": "{b}",
    "v_cndmask_b32": "((({c} >> lane) & 1u) != 0 ? {b} : {a})",
    "v_mul_hi_i32_i24": "MulHiI32(asuint((asint({a}) << 8) >> 8), asuint((asint({b}) << 8) >> 8))",
    "v_cvt_flr_i32_f32": "FloorToI32({a}, false)",
    "v_cvt_rpi_i32_f32": "FloorToI32({a}, true)",
    "v_cvt_off_f32_i4": "asuint((float)((asint({a}) << 28) >> 28) * 0.0625f)",
    "v_rcp_iflag_f32": "asuint(rcp(asfloat({a})))",
    "v_ffbh_i32": "LeadingSignsI32({a})",
    "v_frexp_exp_i32_f32": "FrexpExpF32({a})",
    "v_frexp_mant_f32": "FrexpMantF32({a})",
    "v_fmac_legacy_f32": "FmaLegacyF32({a}, {b}, {d})",
    "v_madmk_f32": "asuint(mad(asfloat({a}), asfloat({k}), asfloat({b})))",
    "v_madak_f32": "asuint(mad(asfloat({a}), asfloat({b}), asfloat({k})))",
    "v_mul_lo_i32": "({a} * {b})",
    "v_sad_u8": "(SadU8({a}, {b}) + {c})",
    "v_sad_hi_u8": "((SadU8({a}, {b}) << 16) + {c})",
    "v_lerp_u8": "LerpU8({a}, {b}, {c})",
    "v_cubeid_f32": "asuint(Cube({a}, {b}, {c}).x)",
    "v_cubesc_f32": "asuint(Cube({a}, {b}, {c}).y)",
    "v_cubetc_f32": "asuint(Cube({a}, {b}, {c}).z)",
    "v_cubema_f32": "asuint(Cube({a}, {b}, {c}).w)",
}
COMPARE = re.compile(r"^v_cmp(x?)_(f|lt|eq|le|gt|lg|ge|ne|neq|t|tru|o|u|nge|nlg|ngt|nle|nlt|class)"
                     r"_(f32|u32|i32)$")
CONSTANT_TESTS = {"f": "false", "t": "true", "tru": "true"}
# Tests flottants non ordonnés (vrais si une source est NaN) : négation du test ordonné.
UNORDERED_F32 = {
    "o": "(!IsNanF32({a}) && !IsNanF32({b}))", "u": "(IsNanF32({a}) || IsNanF32({b}))",
    "nge": "!(asfloat({a}) >= asfloat({b}))", "nlg": "!(asfloat({a}) < asfloat({b}) || asfloat({a}) > asfloat({b}))",
    "ngt": "!(asfloat({a}) > asfloat({b}))", "nle": "!(asfloat({a}) <= asfloat({b}))",
    "nlt": "!(asfloat({a}) < asfloat({b}))", "class": "((({b}) >> ClassF32({a})) & 1u) != 0u",
}


def compare_condition(name, a, b):
    found = COMPARE.match(name)
    operation, kind = found.group(2), found.group(3)
    if operation in CONSTANT_TESTS:
        return CONSTANT_TESTS[operation]
    if operation in UNORDERED_F32:
        if kind != "f32":
            raise Untranslatable(f"non traduite en HLSL : {name}")
        return UNORDERED_F32[operation].format(a=a, b=b)
    cast = {"f32": "asfloat", "u32": "", "i32": "asint"}[kind]
    symbol = COMPARE_OPERATORS[operation]
    if operation == "lg" and kind == "f32":            # ordonné et différent
        return f"({cast}({a}) < {cast}({b}) || {cast}({a}) > {cast}({b}))"
    return f"{cast}({a}) {symbol} {cast}({b})"


def is_compare(name):
    return bool(COMPARE.match(name))
