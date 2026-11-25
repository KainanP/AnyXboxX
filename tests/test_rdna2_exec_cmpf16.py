"""Half-precision compares v_cmp[x]_*_f16 and v_cmp[x]_class_f16 (VOPC, VOP3) in the reference interpreter.

Semantics: AMD "RDNA 2" ISA (November 2020), section 12.9 (p. 156-161): S0[15:0] against S1[15:0] as
binary16, the class bits of V_CMP_CLASS_F16 and its f16-format mask; section 3.9: the mask is fully written
(inactive lanes cleared); section 6.2.5: no OPSEL on VOPC in VOP3. Inline floats are binary16 values (LLVM's
getInlineImmValF16); f16 denormals compare by value (assumed MODE, emu/rdna2_exec_cmpf16.py).
Expected values are written by hand below (RELATIONS, CLASSES); the GPU parity is in test_rdna2_hlsl_cmpf16.py.
"""
import pytest

from emu import rdna2_exec, rdna2_exec_cmpf16, rdna2_hlsl
from test_rdna2_exec import V, const, program, vop1, vop3, vopc
from test_rdna2_sdwa_dpp_exec import DPP16, DPP8, SDWA, dpp16_word, dpp8_word, sdwa_word

LITERAL, MINUS_ONE, HALF, ONE, TWO, ONE_OVER_TWO_PI = 255, 193, 240, 242, 244, 248
VCC_LO, EXEC_LO = 106, 126
ALL = 0xFFFF_FFFF
PARTIAL = 0x0F0F_F0F3

# (S0, S1, relation of the low halves as binary16: "lt", "eq", "gt" or "un" when either is NaN). The high
# halves are junk that a 32-bit compare would see.
RELATIONS = [
    (0x1234_3C00, 0xABCD_4000, "lt"),       # 1.0 < 2.0
    (0xFFFF_8000, 0x0000_0000, "eq"),       # -0 == +0
    (0x0000_0001, 0xFFFF_0000, "gt"),       # smallest denormal > +0 (denormals kept)
    (0x7FFF_8001, 0x8000_0000, "lt"),       # -denormal < +0
    (0x0000_7C00, 0x0000_7BFF, "gt"),       # +inf > 65504
    (0x5555_FC00, 0xAAAA_FBFF, "lt"),       # -inf < -65504
    (0x0000_7E00, 0x0000_7E00, "un"),       # qNaN, qNaN
    (0x3C00_7C01, 0x0000_3C00, "un"),       # sNaN, 1.0
    (0x0000_3C00, 0x0000_FE00, "un"),       # 1.0, -qNaN
    (0xDEAD_BC00, 0xBEEF_C000, "gt"),       # -1.0 > -2.0
    (0x0001_03FF, 0x0002_0400, "lt"),       # largest denormal < smallest normal
    (0x1111_3555, 0x2222_3555, "eq"),       # same low half, different high halves
    (0x0000_7FFF, 0x0000_7C00, "un"),       # NaN with every mantissa bit, +inf
    (0x0000_FBFF, 0x0000_7BFF, "lt"),
    (0x8000_7C00, 0x0000_7C00, "eq"),       # +inf == +inf
    (0x0000_0000, 0x3C00_0000, "eq"),
]
HOLDS = {"f": set(), "lt": {"lt"}, "eq": {"eq"}, "le": {"lt", "eq"}, "gt": {"gt"}, "lg": {"lt", "gt"},
         "ge": {"gt", "eq"}, "o": {"lt", "eq", "gt"}, "u": {"un"}, "nge": {"lt", "un"}, "nlg": {"eq", "un"},
         "ngt": {"lt", "eq", "un"}, "nle": {"gt", "un"}, "neq": {"lt", "gt", "un"}, "nlt": {"gt", "eq", "un"},
         "tru": {"lt", "eq", "gt", "un"}}
NAMES = [f"v_cmp_{predicate}_f16" for predicate in HOLDS]
# (binary16 word, class bit): the ten IEEE classes of V_CMP_CLASS_F16.
CLASSES = [(0x7C01, 0), (0xFDFF, 0), (0x7E00, 1), (0xFFFF, 1), (0xFC00, 2), (0xBC00, 3), (0xFBFF, 3),
           (0x8001, 4), (0x83FF, 4), (0x8000, 5), (0x0000, 6), (0x0001, 7), (0x03FF, 7), (0x0400, 8),
           (0x3C00, 8), (0x7C00, 9)]


def lanes(values, count=32):
    return [values[lane % len(values)] for lane in range(count)]


def expected_mask(predicate, count=32, exec_mask=ALL):
    mask = sum(1 << lane for lane in range(count) if RELATIONS[lane % len(RELATIONS)][2] in HOLDS[predicate])
    return mask & exec_mask


def run(words, exec_mask=ALL, preload=0x1234_5678, count=32):
    wave = rdna2_exec.Wave(lanes=count)
    wave.v[1] = lanes([a for a, _, _ in RELATIONS], count)
    wave.v[2] = lanes([b for _, b, _ in RELATIONS], count)
    for number in (VCC_LO, VCC_LO + 1, *range(40, 60)):
        wave.s[number] = preload
    wave.write_mask(EXEC_LO, exec_mask)
    return rdna2_exec.run(program(*words), wave)


def test_every_f16_compare_encoding_is_executable():
    assert len(rdna2_exec_cmpf16.COMPARES) == 34
    for name in rdna2_exec_cmpf16.COMPARES:
        assert rdna2_exec.executable("VOPC", name) and rdna2_exec.executable("VOP3", name), name


@pytest.mark.parametrize("name", NAMES)
def test_vopc_compares_the_low_halves_as_binary16(name):
    assert run([vopc(name, V + 1, 2)]).vcc == expected_mask(name.split("_")[2])


@pytest.mark.parametrize("name", NAMES)
def test_vop3_writes_the_sgpr_and_clears_inactive_lanes(name):
    wave = run([*vop3(name, 40, V + 1, V + 2)], exec_mask=PARTIAL)
    assert wave.s[40] == expected_mask(name.split("_")[2], exec_mask=PARTIAL)
    assert wave.s[41] == 0x1234_5678                                  # wave32: one SGPR


@pytest.mark.parametrize("name", NAMES)
def test_cmpx_writes_exec_only(name):
    exec_mask = 0xFFFF_00FF
    cmpx = name.replace("v_cmp_", "v_cmpx_")
    vopc_wave = run([vopc(cmpx, V + 1, 2)], exec_mask=exec_mask)
    vop3_wave = run([*vop3(cmpx, EXEC_LO, V + 1, V + 2)], exec_mask=exec_mask)
    expected = expected_mask(name.split("_")[2], exec_mask=exec_mask)
    assert vopc_wave.exec == vop3_wave.exec == expected
    assert vopc_wave.vcc == vop3_wave.vcc == 0x1234_5678


def test_wave64_writes_both_halves_of_the_mask():
    exec_mask = 0xF0F0_FFF3_0FF0_0FF1
    wave = run([*vop3("v_cmp_nge_f16", 40, V + 1, V + 2), vopc("v_cmpx_lg_f16", V + 1, 2)],
               exec_mask=exec_mask, count=64)
    nge, lg = expected_mask("nge", 64, exec_mask), expected_mask("lg", 64, exec_mask)
    assert wave.s[40] | wave.s[41] << 32 == nge
    assert wave.exec == lg


def test_vop3_abs_and_neg_change_the_sign_bit_of_the_half():
    wave = run([
        vop1("v_mov_b32", 3, LITERAL), 0x7FFF_BC00,                    # -1.0 under a junk high half
        vop1("v_mov_b32", 4, LITERAL), 0x0000_C000,                    # -2.0
        *vop3("v_cmp_lt_f16", 40, V + 3, V + 4),                       # -1 < -2 : false
        *vop3("v_cmp_lt_f16", 41, V + 3, V + 4, abs_=0b11),            # 1 < 2
        *vop3("v_cmp_gt_f16", 42, V + 3, V + 4, neg=0b10),             # -1 > 2 : false
        *vop3("v_cmp_eq_f16", 43, V + 3, ONE, neg=0b01),               # 1 == 1.0
        *vop3("v_cmp_eq_f16", 44, V + 3, ONE, abs_=0b01, neg=0b01),    # -|x| = -1 == 1.0 : false
        *vop3("v_cmp_class_f16", 45, V + 3, const(1 << 3)),            # -normal
        *vop3("v_cmp_class_f16", 46, V + 3, const(1 << 3), abs_=0b01),  # |x| is +normal
        *vop3("v_cmp_class_f16", 47, V + 3, LITERAL, neg=0b01), 1 << 8,  # -x is +normal
        *vop3("v_cmp_u_f16", 48, V + 2, V + 1, neg=0b11)])             # the NaN rows stay NaN
    assert wave.s[40:48] == [0, ALL, 0, ALL, 0, ALL, 0, ALL]
    assert wave.s[48] == expected_mask("u")


@pytest.mark.parametrize("word, bit", CLASSES)
def test_class_picks_one_of_ten_bits(word, bit):
    wave = rdna2_exec.run(program(
        vop1("v_mov_b32", 1, LITERAL), 0xABCD_0000 | word,
        vop1("v_mov_b32", 2, LITERAL), 0xFFFF_FC00 | (0x3FF ^ 1 << bit),     # every other class bit
        vop1("v_mov_b32", 3, LITERAL), 0x0000_FC00 | 1 << bit,
        vopc("v_cmp_class_f16", V + 1, 2), *vop3("v_cmp_class_f16", 40, V + 1, V + 3),
        *vop3("v_cmpx_class_f16", EXEC_LO, V + 1, V + 3)))
    assert wave.vcc == 0 and wave.s[40] == ALL and wave.exec == ALL


def test_class_mask_inline_float_is_its_binary16_value():
    # 1/(2*PI) is 0x3118 as an f16 source: bits 3, 4 and 8 (-normal, -denormal, +normal). Its float32
    # pattern 0x3E22F983 would select bits 0, 1, 7 and 8 instead. 1.0 = 0x3C00 selects nothing.
    wave = rdna2_exec.run(program(
        vop1("v_mov_b32", 1, LITERAL), 0x0000_BC00,                    # -1.0
        vop1("v_mov_b32", 2, LITERAL), 0x0000_7E00,                    # qNaN
        vop1("v_mov_b32", 3, LITERAL), 0x0000_8001,                    # -denormal
        *vop3("v_cmp_class_f16", 40, V + 1, ONE_OVER_TWO_PI),
        *vop3("v_cmp_class_f16", 41, V + 2, ONE_OVER_TWO_PI),
        *vop3("v_cmp_class_f16", 42, V + 3, ONE_OVER_TWO_PI),
        *vop3("v_cmp_class_f16", 43, V + 1, ONE),
        *vop3("v_cmp_class_f16", 44, ONE, LITERAL), 1 << 8))          # 1.0 as S0 is +normal
    assert wave.s[40:45] == [ALL, 0, ALL, 0, ALL]


def test_inline_floats_are_binary16_values():
    wave = rdna2_exec.run(program(
        vop1("v_mov_b32", 1, LITERAL), 0x3F00_3800,                    # f16 0.5 under f32 0.5's high half
        vop1("v_mov_b32", 2, LITERAL), 0x0000_3118,                    # f16 1/(2*PI)
        vopc("v_cmp_eq_f16", HALF, 1),
        *vop3("v_cmp_eq_f16", 40, V + 2, ONE_OVER_TWO_PI),
        *vop3("v_cmp_lt_f16", 41, V + 1, ONE),                         # 0.5 < 1.0
        *vop3("v_cmp_gt_f16", 42, TWO, V + 1),                         # 2.0 > 0.5
        *vop3("v_cmp_eq_f16", 43, 247, LITERAL), 0xFFFF_C400))        # -4.0 == literal low half -4.0
    assert wave.vcc == ALL
    assert wave.s[40:44] == [ALL] * 4


def test_integer_constants_and_literals_give_their_low_half():
    wave = rdna2_exec.run(program(
        vop1("v_mov_b32", 1, LITERAL), 0x7777_0001,                    # smallest denormal
        vopc("v_cmp_eq_f16", const(1), 1),                             # 1 = 0x0001
        *vop3("v_cmp_u_f16", 40, MINUS_ONE, V + 1),                    # -1 = 0xFFFF, a NaN
        *vop3("v_cmp_eq_f16", 41, V + 1, LITERAL), 0x3C00_0001,
        *vop3("v_cmp_gt_f16", 42, const(64), V + 1)))                  # 64 = 0x0040, a larger denormal
    assert wave.vcc == ALL
    assert wave.s[40:43] == [ALL, ALL, ALL]


def test_inactive_bits_are_cleared_and_vcc_fully_written():
    wave = run([vopc("v_cmp_tru_f16", V + 1, 2)], exec_mask=0x0000_FFFF, preload=ALL)
    assert wave.vcc == 0x0000_FFFF


@pytest.mark.parametrize("words, name, message", [
    (vop3("v_cmp_lt_f16", 40, V + 1, V + 2, op_sel=0b0001), "v_cmp_lt_f16", "op_sel"),
    (vop3("v_cmpx_ge_f16", EXEC_LO, V + 1, V + 2, op_sel=0b0010), "v_cmpx_ge_f16", "op_sel"),
    (vop3("v_cmp_eq_f16", 40, V + 1, V + 2, clamp=1), "v_cmp_eq_f16", "clamp"),
    (vop3("v_cmp_o_f16", 40, V + 1, V + 2, omod=1), "v_cmp_o_f16", "omod"),
    (vop3("v_cmp_class_f16", 40, V + 1, V + 2, neg=0b10), "v_cmp_class_f16", "class mask"),
    (vop3("v_cmpx_class_f16", EXEC_LO, V + 1, V + 2, abs_=0b10), "v_cmpx_class_f16", "class mask"),
    ((vopc("v_cmp_lt_f16", SDWA, 2), sdwa_word(1)), "v_cmp_lt_f16", "SDWA/DPP"),
    ((vopc("v_cmpx_class_f16", DPP16, 2), dpp16_word(1, 0xE4)), "v_cmpx_class_f16", "SDWA/DPP"),
    ((vopc("v_cmp_neq_f16", DPP8, 2), dpp8_word(1, range(8))), "v_cmp_neq_f16", "SDWA/DPP"),
])
def test_unverified_forms_are_refused_by_name(words, name, message):
    code = program(*words)
    with pytest.raises(rdna2_exec.Untranslated, match=f"(?=.*{name})(?=.*{message})"):
        rdna2_exec.run(code)
    with pytest.raises(rdna2_hlsl.Untranslatable, match=f"(?=.*{name})(?=.*{message})"):
        rdna2_hlsl.translate(code)
    with pytest.raises(rdna2_hlsl.Untranslatable, match=f"(?=.*{name})(?=.*{message})"):
        rdna2_hlsl.translate(code, wave_size=64)
