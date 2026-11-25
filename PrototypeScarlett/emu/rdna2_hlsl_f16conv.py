"""f16 rounding, conversions and packs in the HLSL recompiler, with the semantics of emu/rdna2_exec_f16conv.py.

Integer-only (no float arithmetic, no 64-bit type, no loop): every result is built from the f16 or f32 bits, so it
does not depend on how a driver treats denormals or folds float operations, and it runs on GPUs without FP64. The
f16 helpers of emu/rdna2_hlsl_f16.py (F32ToF16, F16IsNan, F16Min, F16Max, F16Clamp) are reused, not redefined.
"""
from emu.rdna2_exec_f16 import EXTENSIONS, INLINE_HALVES, VGPR_FIRST
from emu.rdna2_exec_f16conv import CLAMP_SATURATES, OPERATIONS, refusal
from emu.rdna2_hlsl_ops import Untranslatable, hexa, source

HELPERS = """uint F16RoundInt(uint h, uint mode) {     // mode 0 trunc, 1 floor, 2 ceil, 3 to nearest even
  uint s = h & 0x8000u, a = h & 0x7FFFu, e = a >> 10;
  if (a > 0x7C00u) return 0x7E00u;            // NaN
  if (e >= 25u) return h;                     // |x| >= 1024 (an integer) or infinity: unchanged
  bool up;
  if (e < 15u) {                              // |x| < 1: a zero or one of its sign
    bool nonzero = a != 0u;
    up = mode == 1u ? (s != 0u && nonzero) : (mode == 2u ? (s == 0u && nonzero) : (mode == 3u && a > 0x3800u));
    return s | (up ? 0x3C00u : 0u);
  }
  uint f = 25u - e, mask = (1u << f) - 1u, rest = h & mask, half = 1u << (f - 1u);
  bool odd = ((h >> f) & 1u) != 0u;
  up = mode == 1u ? (s != 0u && rest != 0u) : (mode == 2u ? (s == 0u && rest != 0u)
       : (mode == 3u && (rest > half || (rest == half && odd))));
  return (h & ~mask) + (up ? 1u << f : 0u);   // a carry out of the significand moves the exponent up
}
uint F16Fract(uint h) {
  uint a = h & 0x7FFFu, e = a >> 10;
  if (a >= 0x7C00u) return 0x7E00u;          // NaN, fract(+-inf)
  if (e >= 25u) return 0u;                    // an integer
  uint k = max(e, 1u), shift = 25u - k;       // |x| = m * 2^-shift
  uint m = e != 0u ? (a & 0x3FFu) | 0x400u : a;
  uint rest = m & ((1u << shift) - 1u);
  if (rest == 0u) return 0u;
  uint n = (h & 0x8000u) != 0u ? (1u << shift) - rest : rest;    // fract = n * 2^-shift, n < 2^24
  uint r = F32ToF16(asuint((float)n) - (shift << 23));          // n is exact in f32: one f16 rounding
  return r == 0x3C00u ? 0x3BFFu : r;
}
uint F16FrexpMant(uint h) {
  uint a = h & 0x7FFFu, e = a >> 10;
  if (a == 0u || e == 31u) return h;
  if (e != 0u) return (h & 0x83FFu) | 0x3800u;
  uint p = firstbithigh(a);                   // denormal: normalized
  return (h & 0x8000u) | 0x3800u | ((a << (10u - p)) & 0x3FFu);
}
uint F16FrexpExp(uint h) {
  uint a = h & 0x7FFFu, e = a >> 10;
  if (a == 0u || e == 31u) return 0u;
  return (e != 0u ? e - 14u : firstbithigh(a) - 23u) & 0xFFFFu;
}
uint F16Magnitude(uint a) {                   // integer part of a finite |x| >= 1 (a = bits without the sign)
  uint e = a >> 10, m = (a & 0x3FFu) | 0x400u;
  return e >= 25u ? m << (e - 25u) : m >> (25u - e);
}
uint F16ToU16(uint h) {
  uint a = h & 0x7FFFu;
  if (a > 0x7C00u || (h & 0x8000u) != 0u || a < 0x3C00u) return 0u;
  return a == 0x7C00u ? 0xFFFFu : F16Magnitude(a);
}
uint F16ToI16(uint h) {
  uint a = h & 0x7FFFu;
  if (a > 0x7C00u || a < 0x3C00u) return 0u;
  uint m = a >= 0x7800u ? 0x8000u : F16Magnitude(a);         // 0x7800 = 32768, infinity included
  if ((h & 0x8000u) != 0u) return (0u - m) & 0xFFFFu;
  return m > 0x7FFFu ? 0x7FFFu : m;
}
uint RoundShift(uint p, uint shift) {         // p / 2^shift rounded to nearest even, 1 <= shift <= 31
  uint q = p >> shift, rest = p & ((1u << shift) - 1u), half = 1u << (shift - 1u);
  return q + ((rest > half || (rest == half && (q & 1u) != 0u)) ? 1u : 0u);
}
uint F16Norm(uint h, uint scale, bool isSigned) {   // round_even(x limited to [-1 or 0, 1] * scale), NaN -> 0
  uint a = h & 0x7FFFu, e = a >> 10;
  bool negative = (h & 0x8000u) != 0u;
  if (a > 0x7C00u || (negative && !isSigned)) return 0u;
  uint q = scale;
  if (a < 0x3C00u) {
    uint m = e != 0u ? (a & 0x3FFu) | 0x400u : a;
    q = RoundShift(m * scale, 25u - max(e, 1u));                // m * scale < 2^27, shift 11..24
  }
  return negative ? (0u - q) & 0xFFFFu : q;
}
uint F32Norm16(uint f, uint scale, bool isSigned) { // the same from an f32, on a 40-bit product in two words
  uint a = f & 0x7FFFFFFFu, e = a >> 23;
  bool negative = (f >> 31) != 0u;
  if (a > 0x7F800000u || (negative && !isSigned)) return 0u;
  uint q = scale;
  if (a < 0x3F800000u) {
    uint shift = 150u - e;                    // |x| = m * 2^-shift, shift >= 24
    if (shift > 40u) {
      q = 0u;                                 // the product is below 2^40 <= half of 2^shift
    } else {
      uint m = (a & 0x7FFFFFu) | 0x800000u;
      uint low = (m & 0xFFFu) * scale, high = (m >> 12) * scale;  // m * scale = high * 2^12 + low
      uint lo = low + (high << 12);
      uint hi = (high >> 20) + (lo < low ? 1u : 0u);
      uint b = shift - 1u;                    // weight of the half bit
      uint quotient = shift >= 32u ? hi >> (shift - 32u) : (lo >> shift) | (hi << (32u - shift));
      bool halfbit = ((b >= 32u ? hi >> (b - 32u) : lo >> b) & 1u) != 0u;
      bool sticky = b >= 32u ? (lo != 0u || (hi & ((1u << (b - 32u)) - 1u)) != 0u) : (lo & ((1u << b) - 1u)) != 0u;
      q = quotient + ((halfbit && (sticky || (quotient & 1u) != 0u)) ? 1u : 0u);
    }
  }
  return negative ? (0u - q) & 0xFFFFu : q;
}
uint F32ToF16Rtz(uint f) {                    // toward zero; a finite overflow gives +-65504
  uint s = (f >> 16) & 0x8000u, a = f & 0x7FFFFFFFu;
  if (a > 0x7F800000u) return 0x7E00u;
  if (a == 0x7F800000u) return s | 0x7C00u;
  if (a >= 0x477FE000u) return s | 0x7BFFu;
  if (a >= 0x38800000u) return s | ((a - 0x38000000u) >> 13);
  if (a < 0x33800000u) return s;
  return s | (((a & 0x7FFFFFu) | 0x800000u) >> (126u - (a >> 23)));
}
uint F16Med3(uint a, uint b, uint c) {       // ISA pseudocode; F16Min/F16Max: emu/rdna2_hlsl_f16.py
  if (F16IsNan(a) || F16IsNan(b) || F16IsNan(c)) return F16Min(F16Min(a, b), c);
  uint m = F16Max(F16Max(a, b), c);
  if (m == a || ((m | a) & 0x7FFFu) == 0u) return F16Max(b, c);    // equal as floats: +0 == -0
  if (m == b || ((m | b) & 0x7FFFu) == 0u) return F16Max(a, c);
  return F16Max(a, b);
}
"""

TEMPLATES = {
    "v_trunc_f16": "F16RoundInt({a}, 0u)", "v_floor_f16": "F16RoundInt({a}, 1u)",
    "v_ceil_f16": "F16RoundInt({a}, 2u)", "v_rndne_f16": "F16RoundInt({a}, 3u)",
    "v_fract_f16": "F16Fract({a})", "v_frexp_mant_f16": "F16FrexpMant({a})", "v_frexp_exp_i16_f16": "F16FrexpExp({a})",
    "v_cvt_f16_u16": "F32ToF16(asuint((float){a}))",
    "v_cvt_f16_i16": "F32ToF16(asuint((float)(asint({a} << 16) >> 16)))",
    "v_cvt_u16_f16": "F16ToU16({a})", "v_cvt_i16_f16": "F16ToI16({a})",
    "v_cvt_norm_i16_f16": "F16Norm({a}, 32767u, true)", "v_cvt_norm_u16_f16": "F16Norm({a}, 65535u, false)",
    "v_cvt_pkrtz_f16_f32": "(F32ToF16Rtz({b}) << 16 | F32ToF16Rtz({a}))",
    "v_cvt_pknorm_i16_f16": "(F16Norm({b}, 32767u, true) << 16 | F16Norm({a}, 32767u, true))",
    "v_cvt_pknorm_u16_f16": "(F16Norm({b}, 65535u, false) << 16 | F16Norm({a}, 65535u, false))",
    "v_cvt_pknorm_i16_f32": "(F32Norm16({b}, 32767u, true) << 16 | F32Norm16({a}, 32767u, true))",
    "v_cvt_pknorm_u16_f32": "(F32Norm16({b}, 65535u, false) << 16 | F32Norm16({a}, 65535u, false))",
    "v_pack_b32_f16": "({b} << 16 | {a})",
    "v_min3_f16": "F16Min(F16Min({a}, {b}), {c})", "v_max3_f16": "F16Max(F16Max({a}, {b}), {c})",
    "v_med3_f16": "F16Med3({a}, {b}, {c})",
}
TRANSLATED = frozenset(TEMPLATES)
assert TRANSLATED == set(OPERATIONS)


def _operand(kind, code, literal, high=False):
    """Source as the interpreter reads it (rdna2_exec_f16conv.source)."""
    if kind == "w":
        return source(code, literal)
    if code < 128 or code >= VGPR_FIRST:
        return f"({source(code, literal)} >> 16)" if high else f"({source(code, literal)} & 0xFFFFu)"
    if code in INLINE_HALVES and kind == "h":
        return hexa(INLINE_HALVES[code])
    return f"({source(code, literal)} & 0xFFFFu)"


def _modified(operand, kind, abs_bit, neg_bit):
    if kind == "i":
        return operand
    if abs_bit:
        operand = f"({operand} & {'0x7FFFFFFFu' if kind == 'w' else '0x7FFFu'})"
    if neg_bit:
        operand = f"({operand} ^ {'0x80000000u' if kind == 'w' else '0x8000u'})"
    return operand


def _assignment(name, d, expression, high=False):
    if OPERATIONS[name][2] == "w":
        return f"v[{d}] = {expression};"
    if high:
        return f"v[{d}] = (v[{d}] & 0xFFFFu) | (({expression}) << 16);"
    return f"v[{d}] = (v[{d}] & 0xFFFF0000u) | ({expression});"


def vector(name, fields, literal, active):
    """VOP1 (unary ops) and VOP2 (v_cvt_pkrtz_f16_f32)."""
    if fields["src0"] in EXTENSIONS:
        raise Untranslatable(f"{name}: SDWA/DPP form (src0 = 0x{fields['src0']:X}) not supported")
    kinds = OPERATIONS[name][0]
    codes = (fields["src0"], VGPR_FIRST + fields["vsrc1"]) if "vsrc1" in fields else (fields["src0"],)
    a, b = ([_operand(kind, code, literal) for kind, code in zip(kinds, codes)] + ["0u"])[:2]
    expression = TEMPLATES[name].format(a=a, b=b, c="0u")
    return [f"if ({active}) {{ {_assignment(name, fields['vdst'], expression)} }}"]


def vop3(name, fields, literal, active):
    reason = refusal(name, fields)
    if reason:
        raise Untranslatable(reason)
    kinds = OPERATIONS[name][0]
    a, b, c = ([_modified(_operand(kind, code, literal, fields.op_sel >> index & 1), kind,
                          fields.abs >> index & 1, fields.neg >> index & 1)
                for index, (kind, code) in enumerate(zip(kinds, fields.sources))] + ["0u", "0u"])[:3]
    expression = TEMPLATES[name].format(a=a, b=b, c=c)
    if fields.clamp and name in CLAMP_SATURATES:
        expression = f"F16Clamp({expression})"
    return [f"if ({active}) {{ {_assignment(name, fields.vdst, expression, fields.op_sel >> 3 & 1)} }}"]
