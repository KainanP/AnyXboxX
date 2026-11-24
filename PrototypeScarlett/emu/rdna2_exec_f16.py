"""Demi-précision (f16) dans l'interpréteur de référence RDNA 2.

Une valeur f16 occupe une moitié de VGPR. Les opérations sont calculées en double précision puis
arrondies une seule fois en binary16, au plus proche pair : pour les sommes, produits et FMA de
valeurs f16, la double précision est exacte chaque fois que l'arrondi f16 en dépend. Les dénormaux
sont conservés (MODE par défaut) ; tout résultat NaN vaut 0x7E00, sans charge utile.
Sémantique d'après la documentation publique d'AMD (« RDNA 2 Instruction Set Architecture »).
"""
import math
import struct

from emu.rdna2_exec_ops import bits_float, float_bits, signed

HALF_NAN, HALF_INFINITY, HALF_ONE = 0x7E00, 0x7C00, 0x3C00
FLOAT_NAN = 0x7FC0_0000
# Constantes flottantes en ligne (codes 240 à 248) lues par une source f16 : leur encodage binary16.
INLINE_HALVES = {240: 0x3800, 241: 0xB800, 242: 0x3C00, 243: 0xBC00, 244: 0x4000, 245: 0xC000, 246: 0x4400,
                 247: 0xC400, 248: 0x3118}


def half_bits(value):
    """Bits binary16 de `value`, arrondi au plus proche pair ; ±infini au-delà du format."""
    if math.isnan(value):
        return HALF_NAN
    try:
        return struct.unpack("<H", struct.pack("<e", value))[0]
    except OverflowError:
        return HALF_INFINITY | (0x8000 if value < 0 else 0)


def bits_half(bits):
    return struct.unpack("<e", struct.pack("<H", bits & 0xFFFF))[0]


def _is_nan(bits):
    return bits & 0x7FFF > HALF_INFINITY


def _order(bits):
    """Clé qui croît avec la valeur (NaN exclus), -0 juste sous +0."""
    return ~bits & 0xFFFF if bits & 0x8000 else bits | 0x8000


def half_min(a, b):
    """v_min_f16 : un NaN cède la place à l'autre opérande, -0 < +0."""
    if _is_nan(a):
        return HALF_NAN if _is_nan(b) else b
    if _is_nan(b):
        return a
    return a if _order(a) <= _order(b) else b


def half_max(a, b):
    if _is_nan(a):
        return HALF_NAN if _is_nan(b) else b
    if _is_nan(b):
        return a
    return a if _order(a) >= _order(b) else b


def half_clamp(bits):
    """clamp de VOP3 sur un résultat f16 : [0, 1], NaN et négatifs (-0 compris) donnent +0."""
    if _is_nan(bits) or bits & 0x8000:
        return 0
    return min(bits, HALF_ONE)


H = bits_half

# Opérations f16 : nom → (types des sources src0..src2, fonction(a, b, c, d, k)).
# Types : « h » moitié f16, « w » mot f32 de 32 bits, « i » entier de 16 bits. `d` : moitié de la
# destination avant l'instruction (accumulateur de fmac) ; `k` : 16 bits bas du littéral.
OPERATIONS = {
    "v_add_f16": ("hh", lambda a, b, c, d, k: half_bits(H(a) + H(b))),
    "v_sub_f16": ("hh", lambda a, b, c, d, k: half_bits(H(a) - H(b))),
    "v_subrev_f16": ("hh", lambda a, b, c, d, k: half_bits(H(b) - H(a))),
    "v_mul_f16": ("hh", lambda a, b, c, d, k: half_bits(H(a) * H(b))),
    "v_fmac_f16": ("hh", lambda a, b, c, d, k: half_bits(H(a) * H(b) + H(d))),
    "v_fmamk_f16": ("hh", lambda a, b, c, d, k: half_bits(H(a) * H(k) + H(b))),
    "v_fmaak_f16": ("hh", lambda a, b, c, d, k: half_bits(H(a) * H(b) + H(k))),
    "v_fma_f16": ("hhh", lambda a, b, c, d, k: half_bits(H(a) * H(b) + H(c))),
    "v_max_f16": ("hh", lambda a, b, c, d, k: half_max(a, b)),
    "v_min_f16": ("hh", lambda a, b, c, d, k: half_min(a, b)),
    # Au-delà de ±64, le résultat f16 vaut déjà 0 ou l'infini : borner l'exposant ne change rien.
    "v_ldexp_f16": ("hi", lambda a, b, c, d, k: half_bits(math.ldexp(H(a), max(-64, min(64, signed(b, 16)))))),
    "v_cvt_f16_f32": ("w", lambda a, b, c, d, k: half_bits(bits_float(a))),
    "v_cvt_f32_f16": ("h", lambda a, b, c, d, k: FLOAT_NAN if _is_nan(a) else float_bits(H(a))),
}
# Résultat sur 32 bits (le VGPR entier) ; les autres écrivent une moitié et gardent l'autre.
WORD_RESULT = frozenset({"v_cvt_f32_f16"})
