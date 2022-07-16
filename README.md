This is a modified version of the cairo compiler, with specific symbolic language support.

### Installing

Clone this repo, and cd to repo root, then use the following command to install it:

```bash
pip install .
```

### Adding verify statements

#### Usage

Use `verify a op b` to add a verify statement, for example:

```cairo
func main():
  [ap] = 1000; ap++
  verify [ap-1] != 0
  ret
end
```

Example testing commands:

```bash
cairo-compile ./tests/test2.cairo --output ./tests/test2_compiled.json
cairo-run --program=./tests/test2_compiled.json --print_output --print_info --relocate_prints --print_memory
```

### Creating A Symbolic Variable

#### Note

Currently this won't create an actual symbolic variable. Instead, it returns a special (and concrete) value `6626069934` as a placeholder.

#### Usage

Use `symbolic(type, tag)` to create a symbolic variable, for example:

```cairo
func main():
    [ap] = 'sym0'; ap++
    [ap] = symbolic(felt, 'sym0'); ap++
    ret
end
```

which compiles to the following bytecodes:

```json
...
"data": [
  "0x480680017fff8000",
  "0x73796d30",
  "0x486680017fff8000",
  "0x73796d30",
  "0x208b7fff7fff7ffe"
],
...
```

Example testing commands:

```
cairo-compile ./tests/test1.cairo --output ./tests/test1_compiled.json
cairo-run --program=./tests/test1_compiled.json --print_output --print_info --relocate_prints --print_memory
```

#### Instruction Decoding

This version adds a new field `SYMBOLIC` to `Instruction.Res`, which now looks like the following:

```python
class Res(Enum):
    # res = operand_1.
    OP1 = 0
    # res = operand_0 + operand_1.
    ADD = auto()
    # res = operand_0 * operand_1.
    MUL = auto()
    # res is not constrained.
    UNCONSTRAINED = auto()
    # res is symbolic
    SYMBOLIC = auto()
```

You can use the following command to test the instruction decoding:

```python
from starkware.cairo.lang.compiler.encode import decode_instruction

# this decodes the line: [ap] = 'sym0'; ap++
# where 0x480680017fff8000 is 5189976364521848832
# and 0x73796d30 is 1937337648
decode_instruction(5189976364521848832,1937337648)
# expected return:
# Instruction(off0=0, off1=-1, off2=1, imm=1937337648, dst_register=<Register.AP: 0>, op0_register=<Register.FP: 1>, op1_addr=<Op1Addr.IMM: 0>, res=<Res.UNCONSTRAINED: 3>, pc_update=<PcUpdate.REGULAR: 0>, ap_update=<ApUpdate.ADD1: 2>, fp_update=<FpUpdate.REGULAR: 0>, opcode=<Opcode.ASSERT_EQ: 1>)

# this decodes the line: [ap] = symbolic(felt, 'sym0'); ap++
# where 0x486680017fff8000 is 5216997962286071808
# and 0x73796d30 is 1937337648
decode_instruction(5216997962286071808,1937337648)
# expected return:
# Instruction(off0=0, off1=-1, off2=1, imm=1937337648, dst_register=<Register.AP: 0>, op0_register=<Register.FP: 1>, op1_addr=<Op1Addr.IMM: 0>, res=<Res.SYMBOLIC: 4>, pc_update=<PcUpdate.REGULAR: 0>, ap_update=<ApUpdate.ADD1: 2>, fp_update=<FpUpdate.REGULAR: 0>, opcode=<Opcode.ASSERT_EQ: 1>)
```

You can see the two instructions are decoded to the same instruction, except for the `res` field: the second one has a special `SYMBOLIC` value set.

### Notes

- Currently only the compiler is modified. The interpreter and other infrastructure remains still, which means they cannot handle the extra `SYMBOLIC` value.
- The `imm` value can be recovered to short text, i.e., `1937337648` can be recovered to `sym0`. You'll need to read cairo source code to do that if you want the original text.
- Currently the type (e.g., `felt`) is not encoded into the instruction. So you can treat every symbolic creation as symbolic integer or symbolic bitvector (depending on the backend type used by the symbolic execution engine).

---

# Introduction

[Cairo](https://cairo-lang.org/) is a programming language for writing provable programs.

# Documentation

The Cairo documentation consists of two parts: "Hello Cairo" and "How Cairo Works?".
Both parts can be found in https://cairo-lang.org/docs/.

We recommend starting from [Setting up the environment](https://cairo-lang.org/docs/quickstart.html).

# Installation instructions

You should be able to download the python package zip file directly from
[github](https://github.com/starkware-libs/cairo-lang/releases/tag/v0.5.2)
and install it using ``pip``.
See [Setting up the environment](https://cairo-lang.org/docs/quickstart.html).

However, if you want to build it yourself, you can build it from the git repository.
It is recommended to run the build inside a docker (as explained below),
since it guarantees that all the dependencies
are installed. Alternatively, you can try following the commands in the
[docker file](https://github.com/starkware-libs/cairo-lang/blob/master/Dockerfile).

## Building using the dockerfile

*Note*: This section is relevant only if you wish to build the Cairo python-package yourself,
rather than downloading it.

The root directory holds a dedicated Dockerfile, which automatically builds the package and runs
the unit tests on a simulated Ubuntu 18.04 environment.
You should have docker installed (see https://docs.docker.com/get-docker/).

Clone the repository and initialize the git submodules using:

```bash
> git clone git@github.com:starkware-libs/cairo-lang.git
> cd cairo-lang
```

Build the docker image:

```bash
> docker build --tag cairo .
```

If everything works, you should see

```bash
Successfully tagged cairo:latest
```

Once the docker image is built, you can fetch the python package zip file using:

```bash
> container_id=$(docker create cairo)
> docker cp ${container_id}:/app/cairo-lang-0.9.0.zip .
> docker rm -v ${container_id}
```

