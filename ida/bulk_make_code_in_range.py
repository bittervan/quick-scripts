# -*- coding: utf-8 -*-
# Bulk "press C" for unknown bytes in a region (RISC-V friendly 2-byte stepping)
import idaapi, idc, ida_bytes, ida_segment, ida_ua

# 可选：手动指定范围（不想用选择/当前段时，填入起止地址）
START_EA = idaapi.BADADDR  # 例如 0x80000000
END_EA   = idaapi.BADADDR  # 例如 0x80010000

def get_range():
    # 优先使用选择范围
    if idaapi.read_selection():
        s, e = idaapi.read_selection()
        return int(s), int(e)
    # 其次使用上面的手动常量
    if START_EA != idaapi.BADADDR and END_EA != idaapi.BADADDR:
        return int(START_EA), int(END_EA)
    # 否则使用当前光标所在段
    ea = idc.here()
    seg = ida_segment.getseg(ea)
    if not seg:
        raise RuntimeError("没有选择范围，也不在任何段内。请框选一段或设置 START_EA/END_EA。")
    return int(seg.start_ea), int(seg.end_ea)

def even_align(ea):
    # RISC-V 支持 RVC，指令起点至少 2 字节对齐
    return ea & ~1

def main():
    s, e = get_range()
    s = even_align(s)
    total = 0
    made  = 0
    ea = s
    print(f"[*] Bulk make-code from 0x{ s:x } to 0x{ e:x }")
    while ea < e:
        flags = ida_bytes.get_full_flags(ea)
        # 仅对未知字节尝试一次“C”（create_insn）
        if idc.isUnknown(flags):
            ida_bytes.del_items(ea, ida_bytes.DELIT_SIMPLE, 0)  # 等价于先 Undefine
            if idc.create_insn(ea) != idaapi.BADADDR:
                insn = ida_ua.insn_t()
                if ida_ua.decode_insn(insn, ea) > 0 and insn.size > 0:
                    step = insn.size
                else:
                    step = 2  # 最小步长按 RVC
                made += 1
                ea += step
                total += 1
                continue
        # 如果不是未知或创建失败，就按 2 字节推进（RVC 友好）
        ea += 2
        total += 1

    idaapi.auto_wait()
    print(f"[+] Done. tried={total}, created_insn={made}")

if __name__ == "__main__":
    main()
