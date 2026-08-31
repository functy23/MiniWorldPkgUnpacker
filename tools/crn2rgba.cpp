// Unpack .CRN textures to raw RGBA.
// usage: crn2rgba <in> <out.rgba> [out.info]
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <cstdint>
#include "crn_decomp_unity.h"
#define ETCDEC_IMPLEMENTATION
#define ETCDEC_STATIC
#include "etcdec.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>



static void dxt1_block(const uint8_t* b, uint8_t* dst, int pitch) {
    uint16_t c0 = b[0] | (b[1] << 8), c1 = b[2] | (b[3] << 8);
    uint32_t bits = b[4] | (b[5] << 8) | (b[6] << 16) | ((uint32_t)b[7] << 24);
    uint8_t pal[4][3];
    auto rgb565 = [](uint16_t v, uint8_t* o) {
        o[0] = (uint8_t)(((v >> 11) & 31) * 255 + 15) / 31;
        o[1] = (uint8_t)(((v >> 5) & 63) * 255 + 31) / 63;
        o[2] = (uint8_t)((v & 31) * 255 + 15) / 31;
    };
    rgb565(c0, pal[0]); rgb565(c1, pal[1]);
    if (c0 > c1) {
        for (int i = 0; i < 3; i++) { pal[2][i] = (2 * pal[0][i] + pal[1][i]) / 3; pal[3][i] = (pal[0][i] + 2 * pal[1][i]) / 3; }
    } else {
        for (int i = 0; i < 3; i++) { pal[2][i] = (pal[0][i] + pal[1][i]) / 2; pal[3][i] = 0; }
    }
    for (int y = 0; y < 4; y++)
        for (int x = 0; x < 4; x++) {
            int idx = (bits >> (2 * (y * 4 + x))) & 3;
            uint8_t* o = dst + y * pitch + x * 4;
            o[0] = pal[idx][0]; o[1] = pal[idx][1]; o[2] = pal[idx][2];
            o[3] = (c0 > c1 || idx != 3) ? 255 : 0;
        }
}

static void dxt45_block(const uint8_t* b, uint8_t* dst, int pitch, bool has_color) {
    // alpha
    uint8_t apal[8];
    apal[0] = b[0]; apal[1] = b[1];
    uint32_t abits = b[2] | (b[3] << 8) | (b[4] << 16) | ((uint32_t)b[5] << 24);
    if (apal[0] > apal[1]) {
        for (int i = 0; i < 6; i++) apal[2 + i] = (uint8_t)(((6 - i) * apal[0] + (1 + i) * apal[1]) / 7);
    } else {
        for (int i = 0; i < 4; i++) apal[2 + i] = (uint8_t)(((4 - i) * apal[0] + (1 + i) * apal[1]) / 5);
        apal[6] = 0; apal[7] = 255;
    }
    for (int y = 0; y < 4; y++)
        for (int x = 0; x < 4; x++) {
            int i = y * 4 + x;
            int idx = (abits >> (3 * i)) & 7;
            dst[y * pitch + x * 4 + 3] = apal[idx];
        }
    if (has_color) ::dxt1_block(b + 8, dst, pitch);
    else for (int y = 0; y < 4; y++) for (int x = 0; x < 4; x++) { dst[y*pitch+x*4] = dst[y*pitch+x*4+1] = dst[y*pitch+x*4+2] = 255; }
}

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s <in> <out.rgba> [out.info]\n", argv[0]); return 1; }
    FILE* f = fopen(argv[1], "rb");
    if (!f) { fprintf(stderr, "open fail\n"); return 1; }
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    std::vector<unsigned char> buf(sz);
    if (fread(buf.data(), 1, sz, f) != (size_t)sz) return 1;
    fclose(f);

    crnd::crn_texture_info ti; ti.m_struct_size = sizeof(crnd::crn_texture_info);
    if (!crnd::crnd_get_texture_info(buf.data(), (unsigned int)sz, &ti)) { fprintf(stderr, "info fail\n"); return 2; }

    std::vector<unsigned char> padded(buf.data(), buf.data() + buf.size());
    padded.insert(padded.end(), 512, 0);
    crnd::crnd_unpack_context ctx = crnd::crnd_unpack_begin(padded.data(), (unsigned int)sz);
    if (!ctx) { fprintf(stderr, "begin fail\n"); return 2; }

    FILE* out = fopen(argv[2], "wb");
    // header: magic, w, h, levels, faces, fmt
    uint32_t hdr[6] = { 0x1A524742u, ti.m_width, ti.m_height, ti.m_levels, ti.m_faces, (uint32_t)ti.m_format };
    fwrite(hdr, 4, 6, out);

    int bpb = (ti.m_format == ::cCRNFmtDXT1 || ti.m_format == ::cCRNFmtDXT5A || ti.m_format == ::cCRNFmtETC1 ||
               ti.m_format == ::cCRNFmtETC2 || ti.m_format == ::cCRNFmtETC1S) ? 8 : 16;
    if (ti.m_format == ::cCRNFmtETC2A) bpb = 16;
    bool is_etc = ti.m_format >= ::cCRNFmtETC1;


    for (unsigned int lvl = 0; lvl < ti.m_levels; lvl++) {
        unsigned int w = ti.m_width >> lvl; if (!w) w = 1;
        unsigned int h = ti.m_height >> lvl; if (!h) h = 1;
        unsigned int bx = (w + 3) / 4, by = (h + 3) / 4;
        unsigned int pitch = bx * bpb;
        unsigned int rawsize = bx * by * bpb;
        std::vector<std::vector<unsigned char>> comps(ti.m_faces, std::vector<unsigned char>(rawsize + 64, 0));
        std::vector<void*> ptrs(ti.m_faces);
        for (unsigned int fc = 0; fc < ti.m_faces; fc++) ptrs[fc] = comps[fc].data();
        fprintf(stderr, "lvl %u w=%u h=%u rawsize=%u\n", lvl, w, h, rawsize);
        if (!crnd::crnd_unpack_level(ctx, ptrs.data(), rawsize, pitch, lvl)) {
            fprintf(stderr, "level %u fail, black\n", lvl);
            for (unsigned int fc = 0; fc < ti.m_faces; fc++) {
                uint32_t wh2[2] = { w, h };
                fwrite(wh2, 4, 2, out);
                std::vector<unsigned char> black((size_t)w * h * 4, 0);
                fwrite(black.data(), 1, black.size(), out);
            }
            continue;
        }
        uint32_t wh[2] = { w, h };
        for (unsigned int fc = 0; fc < ti.m_faces; fc++) {
        fwrite(wh, 4, 2, out);
        std::vector<unsigned char>& comp = comps[fc];
        std::vector<unsigned char> rgba((size_t)w * h * 4, 0);
        std::vector<unsigned char> tmp(4 * 4 * 4, 0);
        for (unsigned int byi = 0; byi < by; byi++)
            for (unsigned int bxi = 0; bxi < bx; bxi++) {
                const unsigned char* blk = comp.data() + (byi * bx + bxi) * (size_t)bpb;
                std::fill(tmp.begin(), tmp.end(), 0);
                if (is_etc) {
                    if (ti.m_format == ::cCRNFmtETC2A) etcdec_eac_rgba(blk, tmp.data(), 16);
                    else if (ti.m_format == ::cCRNFmtETC2AS) etcdec_etc_rgb_a1(blk, tmp.data(), 16);
                    else etcdec_etc_rgb(blk, tmp.data(), 16);
                } else if (ti.m_format == ::cCRNFmtDXT1) dxt1_block(blk, tmp.data(), 16);
                else if (ti.m_format == ::cCRNFmtDXT5A) {
                    dxt45_block(blk, tmp.data(), 16, false);
                } else dxt45_block(blk, tmp.data(), 16, true);
                unsigned int cw = w - bxi * 4; if (cw > 4) cw = 4;
                unsigned int ch = h - byi * 4; if (ch > 4) ch = 4;
                for (unsigned int yy = 0; yy < ch; yy++)
                    for (unsigned int xx = 0; xx < cw; xx++)
                        memcpy(rgba.data() + (((size_t)(byi * 4 + yy) * w) + (bxi * 4 + xx)) * 4,
                               tmp.data() + (yy * 4 + xx) * 4, 4);
            }
        fwrite(rgba.data(), 1, rgba.size(), out);
        }  // faces
        if (getenv("DUMP_BLOCKS")) {
            char bp[256]; snprintf(bp, 256, "%s.blk", argv[2]);
            FILE* bf = fopen(bp, "wb"); for (auto& ccc : comps) fwrite(ccc.data(), 1, rawsize, bf); fclose(bf);
        }
    }
    crnd::crnd_unpack_end(ctx);
    fclose(out);
    if (argc > 3) {
        FILE* info = fopen(argv[3], "w");
        fprintf(info, "%u %u %u %u %d\n", ti.m_width, ti.m_height, ti.m_levels, ti.m_faces, (int)ti.m_format);
        fclose(info);
    }
    return 0;
}
