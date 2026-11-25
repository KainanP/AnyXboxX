"""Half-precision compares of the RDNA 2 reference interpreter: v_cmp[x]_{16 predicates}_f16 and v_cmp[x]_class_f16.

They compare S0[15:0] with S1[15:0] as binary16 values; the high halves are ignored. NaN makes the ordered
predicates false and the unordered ones (u, nge, nlg, ngt, nle, neq, nlt) true, and +0 equals -0 (IEEE 754).
v_cmp_class_f16 tests the IEEE class of S0[15:0] against the mask in S1 (bit 0 sNaN, 1 qNaN, 2 -inf,
3 -normal, 4 -denormal, 5 -0, 6 +0, 7 +denormal, 8 +normal, 9 +inf). Like every compare, the mask is written
whole: bits of inactive lanes are cleared. VOPC writes VCC (v_cmp) or EXEC (v_cmpx), VOP3 an SGPR (v_cmp) or
EXEC (v_cmpx).

Operands are read like the other f16 sources of this interpreter (emu/rdna2_exec_f16.py): a register gives
its low half, an inline float constant its binary16 encoding (1.0 = 0x3C00, 1/(2*PI) = 0x3118), an inline
integer or a literal its low 16 bits. VOP3 abs/neg act on bit 15 of a value operand (S0 and S1, or S0 only
for class).

Sources:
- AMD, "RDNA 2" Instruction Set Architecture, November 2020, section 12.9 "VOPC Instructions": 143
  V_CMP_CLASS_F16 (p. 156: the ten class bits, and "the S1 has a format of f16 since floating point
  literal constants are interpreted as 16 bit value for this opcode"), 159 V_CMPX_CLASS_F16 (p. 157),
  200-207 and 232-239 V_CMP_{F,LT,EQ,LE,GT,LG,GE,O,U,NGE,NLG,NGT,NLE,NEQ,NLT,TRU}_F16, 216-223 and 248-255
  V_CMPX_*_F16 (p. 159-161: "D[threadId] = (S0 < S1)", "EXEC[threadId] = ..."); section 3.9 "Vector
  Compares: VCC and VCCZ" (p. 19-20, "VCC is fully written"); section 6.2.5 "OPSEL Field Restrictions"
  (p. 44: OPSEL is "not for VOP1, VOP2 or VOPC instructions using the VOP3 encoding").
- LLVM 20.1.8, AMDGPUDisassembler.cpp getInlineImmValF16 (inline constants 240-248 of an f16 operand are
  0x3800, 0xB800, 0x3C00, 0xBC00, 0x4000, 0xC000, 0x4400, 0xC400, 0x3118) and AMDGPUBaseInfo.cpp
  isInlinableLiteralFP16 (an inline integer is also valid on an f16 operand, as its bit pattern).
Assumptions (not measured on RDNA 2, open measurement questions): f16 denormals compare by value, i.e. the
shader runs with MODE.FP_DENORM[3:2] = 3 (allow; ISA section 6.4, table 24 p. 47: the mode comes from the
shader's program registers; LLVM's SIModeRegisterDefaults.h defaults FP64FP16Denormals to IEEE), as in this
interpreter's other f16 instructions; a literal or inline integer gives its low 16 bits; VOP3 abs/neg act on
bit 15.
Refused by name until measured: VOP3 op_sel (section 6.2.5), clamp and omod, abs/neg on the class mask,
and the SDWA/DPP forms (like the other f16 instructions of emu/rdna2_exec_f16.py).
"""
from emu.rdna2_exec_f16 import EXTENSIONS, INLINE_HALVES, VGPR_FIRST

HALF_MASK, HALF_SIGN, HALF_INFINITY, HALF_QUIET = 0xFFFF, 0x8000, 0x7C00, 0x0200
EXEC_LO, VCC_LO = 126, 106


def is_nan(bits):
    return bits & 0x7FFF > HALF_INFINITY


def order(bits):
    """Key that grows with the binary16 value, NaN excluded; -0 and +0 share a key."""
    magnitude = bits & 0x7FFF
    return HALF_SIGN - magnitude if bits & HALF_SIGN else HALF_SIGN + magnitude


def half_class(bits):
    """Index (0 to 9) of the IEEE class bit of a binary16 value."""
    negative, exponent, mantissa = bits >> 15 & 1, bits >> 10 & 0x1F, bits & 0x3FF
    if exponent == 0x1F:
        if mantissa:
            return 1 if mantissa & HALF_QUIET else 0
        return 2 if negative else 9
    if exponent == 0:
        if mantissa == 0:
            return 5 if negative else 6
        return 4 if negative else 7
    return 3 if negative else 8


def _ordered(test):
    return lambda a, b: not (is_nan(a) or is_nan(b)) and test(order(a), order(b))


ORDERED = {"lt": lambda x, y: x < y, "eq": lambda x, y: x == y, "le": lambda x, y: x <= y,
           "gt": lambda x, y: x > y, "lg": lambda x, y: x != y, "ge": lambda x, y: x >= y}
TESTS = {"f": lambda a, b: False, "tru": lambda a, b: True,
         "o": lambda a, b: not (is_nan(a) or is_nan(b)), "u": lambda a, b: is_nan(a) or is_nan(b),
         **{name: _ordered(test) for name, test in ORDERED.items()},
         # n<op>: the negation of the ordered test, true when a source is NaN.
         **{f"n{name}": (lambda a, b, t=_ordered(test): not t(a, b))
            for name, test in ORDERED.items()},
         "class": lambda a, b: b >> half_class(a) & 1 == 1}

# {mnemonic: (test on the two 16-bit operands, writes EXEC instead of VCC/SDST)}
COMPARES = {f"{prefix}_{name}_f16": (test, prefix == "v_cmpx")
            for prefix in ("v_cmp", "v_cmpx") for name, test in TESTS.items()}


def _refuse(message, error=None):
    if error is None:
        from emu.rdna2_exec import Untranslated as error
    raise error(message)


def half_source(wave, code, lane, literal):
    """16-bit operand: low half of a register, binary16 inline float, low 16 bits of an integer or literal."""
    if code in INLINE_HALVES:
        return INLINE_HALVES[code]
    return wave.read_lane(code, lane, literal) & HALF_MASK


def check_vopc(name, src0, error=None):
    """Refuse the SDWA/DPP forms (src0 = 0xE9, 0xEA, 0xF9, 0xFA); `error`: exception class to raise."""
    if src0 in EXTENSIONS:
        _refuse(f"{name}: SDWA/DPP form (src0 = 0x{src0:X}) of an f16 compare not supported", error)


def check_vop3(name, fields, error=None):
    """Refuse the VOP3 modifiers whose effect on a compare is not sourced; `error`: exception class to raise."""
    if fields.op_sel:
        _refuse(f"{name} with op_sel (VOP3 compare, 16-bit sources): not usable per the RDNA 2 ISA", error)
    if fields.clamp or fields.omod:
        _refuse(f"{name} with clamp/omod (VOP3 compare): not measured", error)
    if name.endswith("_class_f16") and (fields.abs | fields.neg) >> 1 & 1:
        _refuse(f"{name} with abs/neg on the class mask: not measured", error)


def modify(value, index, abs_bits, neg_bits):
    """VOP3 abs/neg on the sign bit (bit 15) of a binary16 operand."""
    if abs_bits >> index & 1:
        value &= ~HALF_SIGN
    if neg_bits >> index & 1:
        value ^= HALF_SIGN
    return value


def _write(wave, name, mask, destination):
    test, writes_exec = COMPARES[name]
    wave.write_mask(EXEC_LO if writes_exec else destination, mask)


def execute_vopc(wave, name, fields, literal):
    """VOPC form: S0 from src0, S1 from vsrc1; mask in VCC (v_cmp) or EXEC (v_cmpx)."""
    check_vopc(name, fields["src0"])
    test = COMPARES[name][0]
    mask = 0
    for lane in wave.active():
        a = half_source(wave, fields["src0"], lane, literal)
        b = half_source(wave, VGPR_FIRST + fields["vsrc1"], lane, literal)
        mask |= test(a, b) << lane
    _write(wave, name, mask, VCC_LO)


def execute_vop3(wave, name, fields, literal):
    """VOP3 form: mask in the SGPR (pair) of vdst (v_cmp) or EXEC (v_cmpx); abs/neg on bit 15."""
    check_vop3(name, fields)
    test = COMPARES[name][0]
    mask = 0
    for lane in wave.active():
        a, b = (modify(half_source(wave, code, lane, literal), index, fields.abs, fields.neg)
                for index, code in enumerate(fields.sources[:2]))
        mask |= test(a, b) << lane
    _write(wave, name, mask, fields.vdst)
