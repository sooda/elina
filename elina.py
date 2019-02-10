#!/usr/bin/env python3

from sys import argv
from glob import glob
import re
from collections import namedtuple
from sys import stderr

# note: foo_v(foo_f(x)) == x. Many of these are redundant. Every spec is read though to be sure.

# registers
FieldBits = namedtuple("FieldBits", "name field")
FieldValue = namedtuple("FieldValue", "name constant")
Field = namedtuple("Field", "name shift size")
FieldArray = namedtuple("FieldArray", "name shift stride size")
Register = namedtuple("Register", "name address")
RegisterArray = namedtuple("Register", "name address stride")

# "struct" descriptions in RAM
RamBoffset = namedtuple("RamBoffset", "name byteoff")
RamWoffset = namedtuple("RamWoffset", "name wordoff")

def is_single_bit(x):
    return x & (x - 1) == 0

class Registers(object):
    def __init__(self):
        self.func_pat = re.compile(
            r"static inline u32 ([a-z0-9_]+)_([rowsfmv])\((void|u32 v|u32 r|u32 i|u32 r, u32 i|u32 v, u32 i)\)\n"
            "{\n"
            "\treturn (.*);\n"
            "}",
            re.MULTILINE)
        self.parsers = {
            "r void": (re.compile(r"^0x([0-9a-f]{8})U$"),
                self.parse_reg),
            "r u32 i": (re.compile(r"^0x([0-9a-f]{8})U \+ i\*(\d+)U$"),
                self.parse_reg_array),
            "o void": (re.compile(r"^0x([0-9a-f]{8})U$"),
                self.parse_boffset),
            "w void": (re.compile(r"^(\d+)U$"),
                self.parse_woffset),
            "s void": (re.compile(r"^(\d+)U$"),
                self.parse_size),
            "f void": (re.compile(r"^0x([0-9a-f]+)U$"),
                self.parse_field_bits),
            "f u32 v": (re.compile(r"^\(v & 0x([0-9a-f]+)U\) \<\< (\d+)U$"),
                self.parse_val_construct),
            "f u32 v, u32 i": (re.compile(r"^\(v & 0x([0-9a-f]+)U\) \<\< \((\d+)U \+ i\*(\d+)U\)$"),
                self.parse_val_arr_construct),
            "m void": (re.compile(r"^0x([0-9a-f]+)U \<\< (\d+)U$"),
                self.parse_mask),
            "m u32 i": (re.compile(r"^0x([0-9a-f]+)U \<\< \((\d+)U \+ i\*(\d+)U\)$"),
                self.parse_mask_arr),
            "v void": (re.compile(r"^0x([0-9a-f]{8})U$"),
                self.parse_field_value),
            "v u32 r": (re.compile(r"^\(r \>\> (\d+)U\) & 0x([0-9a-f]+)U$"),
                self.parse_val_extract),
            "v u32 r, u32 i": (re.compile(r"^\(r \>\> \((\d+)U \+ i\*(\d+)U\)\) & 0x([0-9a-f]+)U$"),
                self.parse_val_arr_extract),
        }
        self.registers = {}
        self.ramregs = {}
        self.fields = {}
        self.fieldmap = {}

    def get_register(self, name):
        return self.registers[name]

    def read_header(self, header_path):
        #print(header_path)
        contents = open(header_path).read()

        last_reg = None
        for (name, kind, args, ret) in self.func_pat.findall(contents):
            full_kind = "%s %s" % (kind, args)
            # note: not all possible combinations of kind and args exist
            (regex, func) = self.parsers[full_kind]
            parsed = func(name, regex.match(ret))
            #print("    <%s> <%s> <%s> <%s>" % (name,full_kind,ret,parsed))
            # XXX: maybe this should be done in the parser funcs already?
            if kind == "r":
                assert name not in self.registers
                self.registers[name] = parsed
                last_reg = parsed
            elif kind == "o" or kind == "w":
                assert name not in self.ramregs
                self.ramregs[name] = parsed
                last_reg = parsed
            elif kind != "s" and type(parsed) is Field or type(parsed) is FieldArray:
                if name in self.fields:
                    f = self.fields[name]
                    assert type(f) == type(parsed)
                    assert parsed.shift == f.shift
                    assert parsed.size == f.size
                    if type(parsed) is FieldArray:
                        assert parsed.stride == f.stride
                else:
                    if name.startswith(last_reg.name + "_"):
                        self.fieldmap.setdefault(last_reg.name, []).append(parsed)
                    else:
                        stderr.write("warn: %s does not have a parent register\n" % str(parsed))
                self.fields[name] = parsed
            elif type(parsed) is FieldBits:
                # These should ideally have a master field containing the bits,
                # like an enum. That doesn't seem to always be the case though,
                # so we'll do this with slightly less structure. If this is a
                # lone bit, this is likely useful in bitfield specs. False
                # positives may occur.
                assert name not in self.fields
                if parsed.field != 0 and is_single_bit(parsed.field):
                    # spawn a fake field because this doesn't have a shift natively
                    # note: lsb is shifted by 0, so subtract one
                    fake = Field(name=parsed.name, shift=parsed.field.bit_length() - 1, size=1)
                    if name in self.fields:
                        sys.stderr.write("warn!! %s\n" % name)
                    else:
                        if name.startswith(last_reg.name + "_"):
                            self.fieldmap.setdefault(last_reg.name, []).append(fake)
                        else:
                            stderr.write("warn: %s does not have a parent register\n" % str(parsed))
                    self.fields[name] = fake

    def parse_reg(self, name, ret):
        # foo_r(void)
        # 0x00000042U
        (addr,) = ret.groups()
        return Register(name=name, address=int(addr, 16))

    def parse_reg_array(self, name, ret):
        # foo_r(u32 i)
        # 0x00000042U + i*4U
        (base, stride) = ret.groups()
        return RegisterArray(name=name, address=int(base, 16), stride=int(stride))

    def parse_boffset(self, name, ret):
        # foo_o(void)
        # 0x00000042U
        (off,) = ret.groups()
        return RamBoffset(name=name, byteoff=int(off, 16))

    def parse_woffset(self, name, ret):
        # foo_w(void)
        # 0x42U
        (off,) = ret.groups()
        return RamWoffset(name=name, wordoff=int(off))

    def parse_size(self, name, ret):
        # foo_s(void)
        # 42U
        (size,) = ret.groups()
        return Field(name=name, shift=None, size=int(size))

    def parse_field_bits(self, name, ret):
        # foo_f(void)
        # 0x42U
        # (IMO would make sense to pad to 8 long though as it's a field shifted in)
        (value,) = ret.groups()
        return FieldBits(name=name, field=int(value, 16))

    def parse_val_construct(self, name, ret):
        # foo_f(u32 v)
        # (v & 0x1fU) << 42U
        (mask, shift) = ret.groups()
        mask = int(mask, 16)
        assert is_single_bit(mask + 1)
        return Field(name=name, shift=int(shift), size=mask.bit_length())

    def parse_val_arr_construct(self, name, ret):
        # foo_f(u32 v, u32 i)
        # (v & 0x1fU) << (42U + i*1337U)
        (mask, shift, stride) = ret.groups()
        mask = int(mask, 16)
        assert is_single_bit(mask + 1)
        # (size probably equals stride if no gaps in between)
        return FieldArray(name=name, shift=int(shift), stride=int(stride), size=mask.bit_length())

    def parse_mask(self, name, ret):
        # foo_m(void)
        # (0x1fU) << 42U
        (mask, shift) = ret.groups()
        mask = int(mask, 16)
        assert is_single_bit(mask + 1)
        return Field(name=name, shift=int(shift), size=mask.bit_length())

    def parse_mask_arr(self, name, ret):
        # foo_m(u32 i)
        # (0x1fU) << (42U + i*1337U)
        (mask, shift, stride) = ret.groups()
        mask = int(mask, 16)
        assert is_single_bit(mask + 1)
        return FieldArray(name=name, shift=int(shift), stride=int(stride), size=mask.bit_length())

    def parse_field_value(self, name, ret):
        # foo_v(void)
        # 0x00000042U
        # (IMO would make sense to not be padded to 8 long as it's a number, not shifted in)
        (value,) = ret.groups()
        return FieldValue(name=name, constant=int(value, 16))

    def parse_val_extract(self, name, ret):
        # foo_v(u32 r)
        # (r >> 42U) & 0x1fU
        (shift, mask) = ret.groups()
        mask = int(mask, 16)
        assert is_single_bit(mask + 1)
        return Field(name=name, shift=int(shift), size=mask.bit_length())

    def parse_val_arr_extract(self, name, ret):
        # foo_v(u32 r, u32 i)
        # (r >> (42U + i*1337U)) & 0x1fU
        (shift, stride, mask) = ret.groups()
        mask = int(mask, 16)
        assert is_single_bit(mask + 1)
        # (size probably equals stride if no gaps in between)
        return FieldArray(name=name, shift=int(shift), stride=int(stride), size=mask.bit_length())

def main():
    # see https://nv-tegra.nvidia.com/gitweb/?p=linux-nvgpu.git
    # look in drivers/gpu/nvgpu/include/nvgpu/hw/<chip>
    header_path = argv[1]

    headers = glob(header_path + "/*.h")
    r = Registers()

    for header in headers:
        r.read_header(header)

if __name__ == "__main__":
    main()
