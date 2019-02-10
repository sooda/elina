#!/usr/bin/env python3

from elina import Registers
from sys import argv
from glob import glob

def print_reg(r, properties):
    access_type = properties[0]
    try:
        count = int(properties[1])
    except IndexError:
        count = 1
    if count > 1:
        if r.stride != 4:
            raise ValueError("don't know how to handle these yet")
        print("    %s: [%s<u32, %s::Register>; %d]," % (r.name, access_type, r.name.upper(), count))
    else:
        print("    %s: %s<u32, %s::Register>," % (r.name, access_type, r.name.upper()))

def print_regs(regs, properties):
    """
    _gap_foo0: [u8; 0xc0ffee00 - (0x0000dead + 1*4)],
    foo_bar: ReadOnly<u32, FOO_BAR::Register>,
    foo_zing: ReadWrite<u32, FOO_ZING::Register>,
    _gap_foo1: [u8; 0xf00f0000 - (0xc0ffee00 + 2*4)],
    """
    print("#[repr(C)]")
    print("struct Registers {")
    print_reg(regs[0], properties[regs[0].name])

    prev_section_name = regs[0].name.split("_")[0]
    section_gap_count = 1 # implicit gap in front of the first reg
    run_start = regs[0].address
    # gap reference is the previous mentioned reg addr,
    # this much gap between first and last in a consecutive run
    run_length = 1

    for (prev, curr) in zip(regs, regs[1:]):
        delta = curr.address - prev.address
        if delta > 4:
            section_name = curr.name.split("_")[0]
            if section_name != prev_section_name:
                # another section begins, so reset naming
                prev_section_name = section_name
                section_gap_count = 0

            print("    _gap_%s%d: [u8; 0x%08x - (0x%08x + %d*4)]," % (
                section_name, section_gap_count,
                curr.address, run_start, run_length))

            # new numbers for next gap
            run_length = 0
            section_gap_count += 1
            run_start = curr.address

        print_reg(curr, properties[curr.name])

        try:
            length = int(properties[curr.name][1])
        except IndexError:
            length = 1
        run_length += length

    print("}")

def main():
    header_path = argv[1]
    wanted_regs_path = argv[2]

    headers = glob(header_path + "/*.h")
    r = Registers()

    for header in headers:
        r.read_header(header)

    reg_query = [r.strip().split(": ") for r in open(wanted_regs_path).readlines() if r.strip() != ""]
    reg_query = [(rname, rprops.split(" ")) for (rname, rprops) in reg_query]

    regs = [r.get_register(name) for (name, _) in reg_query]
    regs.sort(key=lambda r: r.address)

    # these are "reg_name: ReadOnly" or "reg_name: ReadWrite"
    # sometimes like "reg_name: ReadWrite 2" for two indexed regs
    properties = dict(reg_query)

    print_regs(regs, properties)

if __name__ == "__main__":
    main()
