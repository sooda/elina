#!/usr/bin/env python3

from elina import Registers
from sys import argv
from glob import glob
from collections import namedtuple
from sys import stderr

Properties = namedtuple("Properties", "access_type repeat")

def regstride(r):
    # meh. strongly typed non-array register with no stride is nice but needs this.
    try:
        return r.stride
    except AttributeError:
        return 4

def print_reg(r, properties, current_struct):
    # stride can be other than 4 - in that case this is a part of a properly sized struct
    if regstride(r) != 4:
        repeat = 1
    else:
        repeat = properties.repeat
    if repeat > 1:
        current_struct.append("    %s: [%s<u32, %s::Register>; %d]," % (
            r.name, properties.access_type, r.name.upper(), repeat))
    else:
        current_struct.append("    %s: %s<u32, %s::Register>," % (
            r.name, properties.access_type, r.name.upper()))

# note: input is a consecutive list
# FIXME: works with our own special reg spec, not fully tested yet for corner cases
def flush_regs(run, properties, current_struct, structs):
    linear_single_regs = all([properties[reg.name].repeat == 1 for reg in run])
    single_array = len(run) == 1 and regstride(run[0]) == 4
    if linear_single_regs or single_array:
        # simple enough
        for reg in run:
            print_reg(reg, properties[reg.name], current_struct)
    else:
        struct_stride = len(run) * 4
        stride_ok = all([regstride(reg) == struct_stride for reg in run])
        size = properties[run[0].name].repeat
        same_size = all([properties[reg.name].repeat == size for reg in run])
        if stride_ok and same_size:
            # HACK - probably should be indexed by section name or something
            name = run[0].name.split("_")[0]

            current_struct.append("    %s: [%s; %d]," % (name, name.capitalize(), size))

            new_struct = []
            for reg in run:
                print_reg(reg, properties[reg.name], new_struct)
            structs.append((name.capitalize(), new_struct))
        else:
            raise RuntimeError("don't know how to handle these yet %s" % run)

def collect_struct(regs, properties, structname, structs):
    current_struct = []

    section_gap_count = 1 # implicit gap in front of the first reg
    current_section_name = regs[0].name.split("_")[0]
    # gap reference is the previous mentioned reg addr, i.e., the first one in
    # this list
    current_run = [regs[0]]

    for (prev, curr) in zip(regs, regs[1:]):
        section_name = curr.name.split("_")[0]
        delta = curr.address - prev.address
        assert delta >= 4
        assert delta % 4 == 0
        if delta > 4 or section_name != current_section_name:
            # must output this run now
            flush_regs(current_run, properties, current_struct, structs)

            if section_name != current_section_name:
                # another section begins, so reset naming
                current_section_name = section_name
                section_gap_count = 0

            if delta > 4:
                # non-consecutive sequence (technically we might use the last
                # reg of one section and the first of another, with no gap in
                # between)
                regs_count = sum([properties[r.name].repeat for r in current_run])
                current_struct.append("    _gap_%s%d: [u8; 0x%08x - (0x%08x + %d*4)]," % (
                    current_section_name, section_gap_count,
                    curr.address, current_run[0].address, regs_count))
            current_run = []
            # new numbers for next gap
            section_gap_count += 1
        current_run.append(curr)
    flush_regs(current_run, properties, current_struct, structs)
    structs.append((structname, current_struct))

def print_regs(regs, properties):
    """
    _gap_foo0: [u8; 0xc0ffee00 - (0x0000dead + 1*4)],
    foo_bar: ReadOnly<u32, FOO_BAR::Register>,
    foo_zing: ReadWrite<u32, FOO_ZING::Register>,
    _gap_foo1: [u8; 0xf00f0000 - (0xc0ffee00 + 2*4)],

    also arrays of consecutive registers supported:
    struct Foo {
        a: ReadWrite<u32, FOO_A::Register>, // stride 8
        b: ReadWrite<u32, FOO_B::Register>, // also stride 8
    }
    struct Registers {
        foo: [Foo; 512],
    }
    """

    structs = []
    collect_struct(regs, properties, "Registers", structs)
    for (name, contents) in structs:
        print("#[repr(C)]")
        print("struct %s {" % name)
        for line in contents:
            print(line)
        print("}")

def print_bitfields(regs, r):
    print("register_bitfields! [")
    print("    u32,")
    for reg in regs:
        print("    %s [" % reg.name.upper())
        fields = r.fieldmap.get(reg.name, [])
        fields.sort(key=lambda f: -f.shift)
        strip = reg.name + "_"
        for field in fields:
            assert field.name.startswith(strip)
            name = field.name[len(strip):].upper()
            try:
                stride = field.stride
                stderr.write("warning: don't know how to deal with these yet %s\n" % str(field))
            except AttributeError:
                print("        %-19s OFFSET(%d) NUMBITS(%d) []," % (
                    name, field.shift, field.size))
        if len(fields) == 0:
            # placeholder
            print("        %-19s OFFSET(%d) NUMBITS(%d) []," % (
                "VALUE", 0, 32))
        print("    ],")
    print("];")

def parse_prop(props):
    ps = props.split(" ")
    try:
        (access_type, repeat) = ps
    except ValueError:
        (access_type, repeat) = (ps[0], "1")
    return Properties(access_type, int(repeat))

def main():
    header_path = argv[1]
    wanted_regs_path = argv[2]

    headers = glob(header_path + "/*.h")
    r = Registers()

    for header in headers:
        r.read_header(header)

    reg_query = [r.strip().split(": ") for r in open(wanted_regs_path).readlines() if r.strip() != ""]
    reg_query = [(rname, parse_prop(rprops)) for (rname, rprops) in reg_query]

    regs = [r.get_register(name) for (name, _) in reg_query]
    regs.sort(key=lambda r: r.address)

    # these are "reg_name: ReadOnly" or "reg_name: ReadWrite"
    # sometimes like "reg_name: ReadWrite 2" for two indexed regs
    properties = dict(reg_query)

    print_bitfields(regs, r)
    print_regs(regs, properties)

if __name__ == "__main__":
    main()
