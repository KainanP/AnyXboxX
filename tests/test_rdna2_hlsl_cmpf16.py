"""Half-precision compares: the HLSL translation against the reference interpreter, byte for byte (wave32, wave64).

Every f16 compare runs in VOPC and VOP3 (abs/neg variants), v_cmp and v_cmpx, under a partial EXEC, on every
ordered pair of 20 boundary halves (+-0, denormals, the normal limits, +-1.0, +-inf, quiet and signalling NaN of
both signs) under junk high halves: 13 dispatches of 32 lanes, 7 of 64 lanes. The class compares read a third
register of random masks. Inline floats, inline integers and literals run in each dispatch too.
"""
import random
import struct

import pytest

import test_rdna2_hlsl_wave64 as wave64
from emu import rdna2_exec, rdna2_exec_cmpf16, rdna2_gpu, rdna2_hlsl, rdna2_hlsl_graphics
from test_rdna2_exec import V, const, sop1, vop1, vop2, vop3, vopc
from test_rdna2_exec_memory import INPUT, OUTPUT, global_
from test_rdna2_graphics import PIXEL_SHADER, VERTEX_SHADER, WIDTH
from test_rdna2_hlsl import compare, store_lane, with_lane_offset

LITERAL, MINUS_ONE, ALL_ONES = 255, 193, 0xFFFF_FFFF
VCC_LO, EXEC_LO, MASK_SGPR, EXEC_COPY = 106, 126, 40, 42
PARTIAL = (0x0F0F_F0F3, 0xF00F_0FF0)          # EXEC low / high (wave64)
FIRST_RESULT = 32                               # v31 holds the store address
SLOTS_PER_BASE = {32: 16, 64: 8}                # stores within the signed 12-bit offset
EDGES = (0x0000, 0x8000, 0x0001, 0x8001, 0x03FF, 0x0400, 0x8400, 0x3BFF, 0x3C00, 0x3C01, 0xBC00, 0x7BFF,
         0xFBFF, 0x7C00, 0xFC00, 0x7C01, 0x7E00, 0xFE00, 0x7FFF, 0x3555)
PAIRS = [(a, b) for a in EDGES for b in EDGES]
random.Random(16).shuffle(PAIRS)                # every dispatch mixes values on both sides
NAMES = sorted(name for name in rdna2_exec_cmpf16.COMPARES if name.startswith("v_cmp_"))
# VOP3 (abs, neg) variants, cycled over the compares; the class mask (S1) never takes a modifier.
MODIFIERS = ((0, 0), (0b11, 0), (0, 0b01), (0b10, 0b11), (0b01, 0b10))
CLASS_MODIFIERS = ((0, 0), (1, 0), (0, 1), (1, 1))
gpu = pytest.mark.skipif(not rdna2_gpu.available(), reason="dxc or anyxboxx_gpu_run.exe missing")


def rounds(count):
    return -(-len(PAIRS) // count)


def parity_memory(round_index, count=32):
    """v1 = S0, v2 = S1 (pairs of this round, junk high halves), v3 = random class masks."""
    generator = random.Random(round_index)
    pairs = [PAIRS[(round_index * count + lane) % len(PAIRS)] for lane in range(count)]
    first = [generator.getrandbits(16) << 16 | a for a, _ in pairs]
    second = [generator.getrandbits(16) << 16 | b for _, b in pairs]
    masks = [generator.getrandbits(32) for _ in range(count)]
    image = bytearray(INPUT + 12 * count)
    struct.pack_into(f"<{3 * count}I", image, INPUT, *first, *second, *masks)
    return bytes(image)


def cases():
    """(compare words, where its mask is written: "vcc", "sgpr" or "exec")."""
    found = []
    for index, name in enumerate(NAMES):
        is_class = name.endswith("_class_f16")
        s1 = 3 if is_class else 2
        for prefix in ("v_cmp_", "v_cmpx_"):
            opcode = name.replace("v_cmp_", prefix)
            writes_exec = prefix == "v_cmpx_"
            abs_, neg = (CLASS_MODIFIERS if is_class else MODIFIERS)[index % (4 if is_class else 5)]
            target = EXEC_LO if writes_exec else MASK_SGPR
            found.append(([vopc(opcode, V + 1, s1)], "exec" if writes_exec else "vcc"))
            found.append(([*vop3(opcode, target, V + 1, V + s1, abs_=abs_, neg=neg)],
                          "exec" if writes_exec else "sgpr"))
    return found + constant_cases()


def constant_cases():
    """Inline floats (binary16 values), inline integers and literals (low halves) as S0 and S1."""
    words = [([vopc("v_cmp_lt_f16", code, 2)], "vcc") for code in range(240, 249)]
    words += [([vopc("v_cmp_eq_f16", const(1), 2)], "vcc"), ([vopc("v_cmpx_u_f16", MINUS_ONE, 2)], "exec"),
              ([vopc("v_cmp_ge_f16", LITERAL, 2), 0xFFFF_3C00], "vcc"),
              ([*vop3("v_cmp_class_f16", MASK_SGPR, V + 1, 248)], "sgpr"),
              ([*vop3("v_cmp_class_f16", MASK_SGPR, V + 1, LITERAL), 0x0000_0383], "sgpr"),
              ([*vop3("v_cmp_nlt_f16", MASK_SGPR, V + 1, 243, neg=0b10)], "sgpr"),
              ([*vop3("v_cmpx_gt_f16", EXEC_LO, 245, V + 2)], "exec"),
              ([*vop3("v_cmp_neq_f16", MASK_SGPR, V + 2, LITERAL, abs_=0b01), 0x1234_7C00], "sgpr")]
    return words


def mask_source(where):
    return {"vcc": VCC_LO, "sgpr": MASK_SGPR, "exec": EXEC_COPY}[where]


def program_words(count):
    """Load the sources, then each compare under a partial EXEC; its mask is copied to VGPRs under a full EXEC."""
    halves = count // 32
    words = [*global_("global_load_dword", addr=31, vdst=1, saddr=0),
             *global_("global_load_dword", addr=31, vdst=2, saddr=0, offset=4 * count),
             *global_("global_load_dword", addr=31, vdst=3, saddr=0, offset=8 * count)]
    result = FIRST_RESULT
    for compare_words, where in cases():
        words += [word for half in range(halves) for word in (sop1("s_mov_b32", EXEC_LO + half, LITERAL),
                                                              PARTIAL[half])]
        words += compare_words
        if where == "exec":
            words += [sop1("s_mov_b32", EXEC_COPY + half, EXEC_LO + half) for half in range(halves)]
        words += [sop1("s_mov_b32", EXEC_LO + half, MINUS_ONE) for half in range(halves)]
        for half in range(halves):
            words.append(vop1("v_mov_b32", result, mask_source(where) + half))
            result += 1
    return words, result - FIRST_RESULT


def parity_program(count=32):
    words, total = program_words(count)
    per_base = SLOTS_PER_BASE[count]
    slot_bytes = 128 if count == 32 else wave64.SLOT
    store = store_lane if count == 32 else wave64.store_lane
    stores = []
    for slot in range(total):
        if slot and slot % per_base == 0:
            stores += [vop2("v_add_nc_u32", 31, LITERAL, 31), per_base * slot_bytes]
        stores += store(FIRST_RESULT + slot, slot % per_base)
    lane_offset = with_lane_offset if count == 32 else wave64.with_lane_offset
    return lane_offset(*words, *stores), total


def test_parity_programs_fit_the_register_file_and_memory():
    for count in (32, 64):
        _, total = parity_program(count)
        slot_bytes = 128 if count == 32 else wave64.SLOT
        assert FIRST_RESULT + total <= 256 and OUTPUT + total * slot_bytes <= 0x40000
    assert rounds(32) * 32 >= len(PAIRS) and rounds(64) * 64 >= len(PAIRS)


def test_hlsl_compares_halves_with_integer_keys():
    hlsl = rdna2_hlsl.translate(parity_program()[0])
    assert "uint F16CmpKey(uint h)" in hlsl and "F16Class(" in hlsl
    assert hlsl.count("F16CmpKey(") > 40 and hlsl.count("Ballot(lane") >= len(cases())


def test_parity_masks_vary_and_respect_exec():
    """Guard for the GPU tests: the masks differ between compares and inactive lanes never get a bit."""
    wave = rdna2_exec.Wave()
    wave.s[0], wave.s[2] = INPUT, OUTPUT
    wave.memory.write(0, parity_memory(3))
    data, total = parity_program()
    rdna2_exec.run(data, wave)
    masks = [wave.v[FIRST_RESULT + i][0] for i in range(total)]
    assert len(set(masks)) > total // 3
    assert all(mask & ~PARTIAL[0] == 0 for mask in masks)


def with_compares(shader):
    """A graphics shader preceded by an f16 compare in VOPC and in VOP3 (masks unused by the shader)."""
    words = [vopc("v_cmp_nlt_f16", V + 0, 0), *vop3("v_cmpx_class_f16", EXEC_LO, V + 0, 248)]
    return struct.pack(f"<{len(words)}I", *words) + shader


def test_vertex_and_pixel_shaders_carry_the_f16_compare_helpers():
    vertex = rdna2_hlsl_graphics.translate_vertex(with_compares(VERTEX_SHADER))
    pixel = rdna2_hlsl_graphics.translate_pixel(with_compares(PIXEL_SHADER), WIDTH)
    for hlsl in (vertex, pixel):
        assert "uint F16CmpKey(uint h)" in hlsl and "F16Class(" in hlsl.split("main(")[1]


@gpu
def test_graphics_shaders_with_f16_compares_compile():
    rdna2_gpu.compile_dxil(rdna2_hlsl_graphics.translate_vertex(with_compares(VERTEX_SHADER)),
                           model=rdna2_gpu.VERTEX_MODEL)
    pixel = rdna2_hlsl_graphics.translate_pixel(with_compares(PIXEL_SHADER), WIDTH)
    model = rdna2_gpu.PIXEL_WAVE_MODEL if "IsHelperLane()" in pixel else rdna2_gpu.PIXEL_MODEL
    rdna2_gpu.compile_dxil(pixel, model=model)


@gpu
@pytest.mark.parametrize("round_index", range(rounds(32)))
def test_f16_compares_match_interpreter_on_gpu(round_index):
    expected, actual = compare(parity_program()[0], memory=parity_memory(round_index))
    assert actual == expected


@gpu
@pytest.mark.parametrize("round_index", range(rounds(64)))
def test_f16_compares_match_interpreter_on_gpu_in_wave64(round_index):
    expected, actual = wave64.compare(parity_program(64)[0], memory=parity_memory(round_index, 64))
    assert actual == expected
