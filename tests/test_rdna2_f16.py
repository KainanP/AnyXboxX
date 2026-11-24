"""Demi-précision (f16) dans l'interpréteur de référence RDNA 2 : valeurs attendues écrites à la main
d'après la documentation ISA d'AMD (arrondi au plus proche pair, dénormaux conservés)."""
import math

from emu import rdna2_exec_f16 as f16
from emu.rdna2_exec_ops import float_bits


def run(name, a=0, b=0, c=0, d=0, k=0):
    return f16.OPERATIONS[name][1](a, b, c, d, k)


def test_rounding_to_half_is_nearest_even():
    cases = {1.0: 0x3C00, 1 + 2**-11: 0x3C00, 1 + 3 * 2**-11: 0x3C02, 65504.0: 0x7BFF, 65519.0: 0x7BFF,
             65520.0: 0x7C00, -65520.0: 0xFC00, 1e9: 0x7C00, 2**-24: 0x0001, 2**-25: 0x0000,
             1.5 * 2**-24: 0x0002, 2**-25 + 2**-40: 0x0001, -0.0: 0x8000}
    for value, bits in cases.items():
        assert f16.half_bits(value) == bits, value
    assert f16.half_bits(math.nan) == f16.half_bits(-math.nan) == 0x7E00


def test_arithmetic_rounds_once():
    assert run("v_add_f16", 0x3C00, 0x3C00) == 0x4000
    assert run("v_add_f16", 0x3C00, 0x1000) == 0x3C00          # 1 + 2^-11 : égalité, pair
    assert run("v_add_f16", 0x3C01, 0x1000) == 0x3C02
    assert run("v_add_f16", 0x7BFF, 0x7BFF) == 0x7C00
    assert run("v_add_f16", 0x7C00, 0xFC00) == 0x7E00
    assert run("v_add_f16", 0x0001, 0x8001) == 0x0000
    assert run("v_add_f16", 0x0400, 0x8001) == 0x03FF
    assert run("v_sub_f16", 0x3C00, 0x3C00) == 0x0000
    assert run("v_subrev_f16", 0x3C00, 0x4000) == 0x3C00
    assert run("v_mul_f16", 0x3C01, 0x3C01) == 0x3C02
    assert run("v_mul_f16", 0x0001, 0x3800) == 0x0000
    assert run("v_mul_f16", 0x0003, 0x3800) == 0x0002
    assert run("v_mul_f16", 0x7C00, 0x0000) == 0x7E00


def test_fused_multiply_add_rounds_once():
    assert run("v_fma_f16", 0x101F, 0x3BC4, 0x3C00) == 0x3C01   # f32 puis f16 donnerait 0x3C00
    assert run("v_fmac_f16", 0x101F, 0x3BC4, d=0x3C00) == 0x3C01
    assert run("v_fmamk_f16", 0x101F, 0x3C00, k=0x3BC4) == 0x3C01
    assert run("v_fmaak_f16", 0x101F, 0x3BC4, k=0x3C00) == 0x3C01


def test_min_and_max_follow_rdna2():
    assert run("v_min_f16", 0x8000, 0x0000) == run("v_min_f16", 0x0000, 0x8000) == 0x8000
    assert run("v_max_f16", 0x8000, 0x0000) == 0x0000
    assert run("v_min_f16", 0x7E00, 0x3C00) == run("v_max_f16", 0x3C00, 0x7E00) == 0x3C00
    assert run("v_min_f16", 0x7E00, 0xFE01) == 0x7E00
    assert run("v_min_f16", 0xFC00, 0x7C00) == 0xFC00
    assert run("v_max_f16", 0xBC00, 0x3C00) == 0x3C00


def test_ldexp_takes_a_signed_16_bit_exponent():
    expected = {1: 0x4000, 0xFFFF: 0x3800, 16: 0x7C00, 0xFFE8: 0x0001, 0xFFE7: 0x0000, 0x7FFF: 0x7C00, 0x8000: 0x0000}
    for exponent, bits in expected.items():
        assert run("v_ldexp_f16", 0x3C00, exponent) == bits, hex(exponent)
    assert run("v_ldexp_f16", 0x3E00, 0xFFE7) == 0x0001           # 1,5 × 2^-25
    assert run("v_ldexp_f16", 0x0001, 0x0001_0001) == 0x0002      # bits 31:16 ignorés


def test_conversions_between_f16_and_f32():
    to_half = {float_bits(1.0): 0x3C00, 0x477F_F000: 0x7C00, 0x477F_EFFF: 0x7BFF, 0x3F80_1000: 0x3C00,
               0x3F80_3000: 0x3C02, 0x0000_0001: 0x0000, 0x8000_0001: 0x8000, 0x33C0_0000: 0x0002,
               0x3300_0000: 0x0000, 0x3300_0001: 0x0001, 0x387F_FFFF: 0x0400, 0x7FC0_0001: 0x7E00,
               0xFF80_0000: 0xFC00, 0xC77F_E000: 0xFBFF}
    for word, bits in to_half.items():
        assert run("v_cvt_f16_f32", word) == bits, hex(word)
    to_word = {0x3C00: 0x3F80_0000, 0x0001: 0x3380_0000, 0x8000: 0x8000_0000, 0x7C00: 0x7F80_0000,
               0x7C01: 0x7FC0_0000, 0xFE00: 0x7FC0_0000}
    for bits, word in to_word.items():
        assert run("v_cvt_f32_f16", bits) == word, hex(bits)


def test_clamp_to_the_unit_interval():
    assert [f16.half_clamp(h) for h in (0x7E00, 0x8000, 0xBC00, 0x4000, 0x3800, 0x7C00)] == \
        [0, 0, 0, 0x3C00, 0x3800, 0x3C00]
