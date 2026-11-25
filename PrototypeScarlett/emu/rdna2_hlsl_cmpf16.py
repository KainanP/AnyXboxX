"""Half-precision compares in the HLSL recompiler, with the semantics of emu/rdna2_exec_cmpf16.py.

Integer-only (no `half`, no f16tof32, no float compare): NaN is tested on the bits, and the ordered tests
compare a key that grows with the binary16 value and gives +0 and -0 the same key, so a driver's float
compare rules (NaN handling, denormal flushing) never enter. The wave32 and wave64 recompilers build the
ballot around `condition`.
"""
from emu.rdna2_exec_cmpf16 import COMPARES, check_vop3, check_vopc
from emu.rdna2_exec_f16 import INLINE_HALVES, VGPR_FIRST
from emu.rdna2_hlsl_ops import Untranslatable, hexa, source

# F16IsNan comes with emu/rdna2_hlsl_f16.py's HELPERS, which every program carries before these.
HELPERS = """uint F16CmpKey(uint h) { uint m = h & 0x7FFFu; return (h & 0x8000u) != 0u ? 0x8000u - m : 0x8000u + m; }
bool F16Ordered(uint a, uint b) { return !F16IsNan(a) && !F16IsNan(b); }
uint F16Class(uint h) {
  uint e = (h >> 10) & 0x1Fu, m = h & 0x3FFu;
  bool negative = (h & 0x8000u) != 0u;
  if (e == 0x1Fu) return m != 0u ? ((m & 0x200u) != 0u ? 1u : 0u) : (negative ? 2u : 9u);
  if (e == 0u) return m == 0u ? (negative ? 5u : 6u) : (negative ? 4u : 7u);
  return negative ? 3u : 8u;
}
"""

ORDERED = {"lt": "<", "eq": "==", "le": "<=", "gt": ">", "lg": "!=", "ge": ">="}


def _test(predicate, a, b):
    if predicate == "f":
        return "false"
    if predicate == "tru":
        return "true"
    if predicate == "o":
        return f"F16Ordered({a}, {b})"
    if predicate == "u":
        return f"!F16Ordered({a}, {b})"
    if predicate == "class":
        return f"((({b}) >> F16Class({a})) & 1u) != 0u"
    negated = predicate.startswith("n")
    symbol = ORDERED[predicate[1:] if negated else predicate]
    ordered = f"(F16Ordered({a}, {b}) && F16CmpKey({a}) {symbol} F16CmpKey({b}))"
    return f"!{ordered}" if negated else ordered


def predicate(name):
    """v_cmpx_nge_f16 → "nge"."""
    return name.split("_")[-2]


def half_operand(code, literal):
    """16-bit operand as in the interpreter: low half, binary16 inline float, low 16 bits of an integer."""
    if code in INLINE_HALVES:
        return hexa(INLINE_HALVES[code])
    return f"({source(code, literal)} & 0xFFFFu)"


def _modified(operand, index, abs_bits, neg_bits):
    if abs_bits >> index & 1:
        operand = f"({operand} & 0x7FFFu)"
    if neg_bits >> index & 1:
        operand = f"({operand} ^ 0x8000u)"
    return operand


def vopc_condition(name, fields, literal):
    """(HLSL condition, writes EXEC) of the VOPC form; its mask goes to VCC or EXEC."""
    check_vopc(name, fields["src0"], Untranslatable)
    a = half_operand(fields["src0"], literal)
    b = half_operand(VGPR_FIRST + fields["vsrc1"], literal)
    return _test(predicate(name), a, b), COMPARES[name][1]


def vop3_condition(name, fields, literal):
    """(HLSL condition, writes EXEC) of the VOP3 form; its mask goes to the SGPR of vdst or EXEC."""
    check_vop3(name, fields, Untranslatable)
    a, b = (_modified(half_operand(code, literal), index, fields.abs, fields.neg)
            for index, code in enumerate(fields.sources[:2]))
    return _test(predicate(name), a, b), COMPARES[name][1]


__all__ = ["COMPARES", "HELPERS", "vopc_condition", "vop3_condition", "Untranslatable"]
