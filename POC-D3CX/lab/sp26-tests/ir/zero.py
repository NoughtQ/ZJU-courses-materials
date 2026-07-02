from __future__ import annotations
from lark import Lark, ast_utils, Transformer, Token
from dataclasses import dataclass
from enum import Enum
import random

import sys
import argparse

DEBUG = False

# -------------------------------- IRNode --------------------------------#


class Op(Enum):
    def __str__(self) -> str:
        return self.value


class BinOp(Op):
    Add = "+"
    Sub = "-"
    Mul = "*"
    Div = "/"
    Rem = "%"
    Sll = "<<"  # 左移
    Sra = ">>"  # 算术右移
    And = "&"
    Or = "|"
    Xor = "^"


class RelOp(Op):
    Gt = ">"
    Ge = ">="
    Lt = "<"
    Le = "<="
    Eq = "=="
    Ne = "!="


class UnOp(Op):
    Neg = "-"
    Pos = "+"


@dataclass
class IRNode(ast_utils.Ast):
    """
    IRNode is the base class for all IR nodes.
    """

    def __str__(self) -> str:
        raise NotImplementedError("IRNode.__str__() is not implemented.")
    
    @property
    def dst_var(self) -> Token | None:
        return None


@dataclass
class Binary(IRNode):
    """
    BinaryOp is the class for all binary operations.
    """

    dst: Token
    left: Token
    op: BinOp
    right: Token

    def __str__(self) -> str:
        return f"{self.dst} := {self.left} {self.op} {self.right}"
    
    @property
    def dst_var(self) -> Token:
        return self.dst


@dataclass
class Binaryi(IRNode):
    """
    BinaryOp is the class for all binary operations.
    """

    dst: Token
    left: Token
    op: BinOp
    right: int

    def __init__(self, dst, left, op, right):
        self.dst = dst
        self.left = left
        self.op = op
        self.right = int(right.value)

    def __str__(self) -> str:
        return f"{self.dst} := {self.left} {self.op} #{self.right}"
    
    @property
    def dst_var(self) -> Token:
        return self.dst


@dataclass
class Unary(IRNode):
    """
    UnaryOp is the class for all unary operations.
    """

    dst: Token
    op: UnOp
    right: Token

    def __str__(self) -> str:
        return f"{self.dst} := {self.op} {self.right}"
    
    @property
    def dst_var(self) -> Token:
        return self.dst


@dataclass
class Store(IRNode):
    """
    Store is a special IRNode for storing a value to a pointer.
    *(x + #k) = y
    """

    left: Token
    offset: int
    right: Token

    def __init__(self, *args: Token):
        if len(args) == 3:
            self.left, offset, self.right = args
            self.offset = int(offset.value)
        elif len(args) == 2:
            self.left, self.right = args
            self.offset = 0

    def __str__(self) -> str:
        if self.offset == 0:
            return f"*{self.left} := {self.right}"
        return f"*({self.left} + #{self.offset}) := {self.right}"


@dataclass
class Deref(IRNode):
    """
    x = *(y + #k)
    """

    left: Token
    right: Token
    offset: int

    def __init__(self, *args: Token):
        if len(args) == 3:
            self.left, self.right, offset = args
            self.offset = int(offset.value)
        elif len(args) == 2:
            self.left, self.right = args
            self.offset = 0

    def __str__(self) -> str:
        if self.offset == 0:
            return f"{self.left} := *{self.right}"
        return f"{self.left} := *({self.right} + #{self.offset})"
    
    @property
    def dst_var(self) -> Token:
        return self.left


@dataclass
class Li(IRNode):
    """
    LoadImm is a special IRNode for loading an immediate value.
    """

    label: Token
    value: int

    def __init__(self, label, token):
        self.label = label
        self.value = int(token.value)

    def __str__(self) -> str:
        return f"{self.label} = #{self.value}"
    
    @property
    def dst_var(self) -> Token:
        return self.label


@dataclass
class Function(IRNode):
    """ Defining a function. """

    name: Token

    def __str__(self) -> str:
        return f"Function {self.name}"


@dataclass
class Label(IRNode):
    """ Defining a label. """

    label: Token

    def __str__(self) -> str:
        return f"Label {self.label}"


@dataclass
class Goto(IRNode):
    """ Jumping to a label. """

    label: Token

    def __str__(self) -> str:
        return f"Goto {self.label}"


@dataclass
class Param(IRNode):
    """ Passing a parameter. """

    name: Token

    def __str__(self) -> str:
        return f"Param {self.name}"
    
    @property
    def dst_var(self) -> Token:
        return self.name


@dataclass
class Assign(IRNode):
    """ Assigning a variable. """

    dst: Token
    src: Token

    def __str__(self) -> str:
        return f"{self.dst} := {self.src}"
    
    @property
    def dst_var(self) -> Token:
        return self.dst


@dataclass
class If(IRNode):
    """ If statement. """

    left: Token
    op: RelOp
    right: Token
    label: Token

    def __str__(self) -> str:
        return f"If {self.left} {self.op} {self.right} Goto {self.label}"


@dataclass
class Return(IRNode):
    """ Returning a value. """

    name: Token | None

    def __init__(self, *args):
        if len(args) == 1:
            self.name = args[0]
        else:
            self.name = None

    def __str__(self) -> str:
        return f"Return {self.name}"


@dataclass
class Arg(IRNode):
    """ Passing an argument. """

    name: Token

    def __str__(self) -> str:
        return f"Arg {self.name}"


@dataclass
class Call(IRNode):
    """ Calling a function. """

    left: Token | None
    right: Token

    def __init__(self, *args):
        if len(args) == 2:
            self.left, self.right = args
        elif len(args) == 1:  # do not have return value
            self.left = None
            self.right = args[0]

    def __str__(self) -> str:
        if self.left:
            return f"{self.left} := Call {self.right}"
        else:
            return f"{self.left} := Call {self.right}"
        
    @property
    def dst_var(self) -> Token | None:
        return self.left


@dataclass
class Dec(IRNode):
    """ Passing an argument. """

    name: Token
    size: int

    def __init__(self, name, token):
        self.name = name
        self.size = int(token.value)
        assert self.size % 4 == 0, "Array size should be multiple of 4."

    def __str__(self) -> str:
        return f"Dec {self.name} #{self.size}"
    
    @property
    def dst_var(self) -> Token:
        return self.name

@dataclass
class La(IRNode):
    """ Load address of a label """

    dst: Token
    label: Token

    def __str__(self) -> str:
        return f"{self.dst} := &{self.label}"
    
    @property
    def dst_var(self) -> Token:
        return self.dst

@dataclass
class Global(IRNode):
    """ Define a global variable """

    name: Token
    size: int
    values: list[int]

    def __init__(self, name, *args):
        self.name = name
        self.size = int(args[0].value)
        assert self.size % 4 == 0, "Array size should be multiple of 4."
        if len(args) > 1:
            self.values = [int(arg.value) for arg in args[1:]]
        else:
            self.values = [0] * (self.size // 4)
        assert len(self.values) * 4 == self.size, "Values size should be equal to array size."  

    def __str__(self) -> str:
        values = ", ".join([f"#{v}" for v in self.values])
        return f"Global {self.name} #{self.size} = {values}"

@dataclass
class Phi(IRNode):
    """ Phi node """
    
    dst: Token
    srcs: dict[Token, Token]
    
    def __init__(self, dst, *srcs):
        self.dst = dst
        self.srcs = {}
        assert len(srcs) % 2 == 0, "srcs should be a list of key-value pairs"
        for i in range(0, len(srcs), 2):
            self.srcs[srcs[i]] = srcs[i + 1]
        
    def __str__(self) -> str:
        srcs = ", ".join([f"[{k}, {v}]" for k, v in self.srcs.items()])
        return f"{self.dst} = PHI {srcs}"
    
    @property
    def dst_var(self) -> Token:
        return self.dst
        

class ToIR(Transformer):
    def start(self, args): return args
    def mul(self, _): return BinOp.Mul
    def div(self, _): return BinOp.Div
    def rem(self, _): return BinOp.Rem
    def add(self, _): return BinOp.Add
    def sub(self, _): return BinOp.Sub
    def gt(self, _): return RelOp.Gt
    def ge(self, _): return RelOp.Ge
    def lt(self, _): return RelOp.Lt
    def le(self, _): return RelOp.Le
    def eq(self, _): return RelOp.Eq
    def ne(self, _): return RelOp.Ne
    def neg(self, _): return UnOp.Neg
    def pos(self, _): return UnOp.Pos
    def sll(self, _): return BinOp.Sll
    def sra(self, _): return BinOp.Sra
    def and_(self, _): return BinOp.And
    def or_(self, _): return BinOp.Or
    def xor(self, _): return BinOp.Xor

# -------------------------------- Parser --------------------------------#


parser = Lark(r"""
start: instruction*

?instruction: "LABEL" NAME ":" -> label
    | "GOTO" NAME -> goto
    | "IF" NAME relop NAME "GOTO" NAME -> if
    | NAME "=" NAME -> assign
    | NAME "=" unop NAME -> unary
    | "*" "(" NAME "+" "#" SIGNED_INT ")" "=" NAME -> store
    | "*" NAME "=" NAME -> store
    | NAME "=" "*" "(" NAME "+" "#" SIGNED_INT ")" -> deref
    | NAME "=" "*" NAME -> deref
    | NAME "=" NAME binop NAME -> binary
    | NAME "=" NAME binop "#" SIGNED_INT -> binaryi
    | NAME "=" "#" SIGNED_INT -> li
    | "PARAM" NAME -> param
    | "ARG" NAME -> arg
    | "RETURN" NAME -> return
    | "RETURN" -> return
    | NAME "=" "CALL" NAME -> call
    | "CALL" NAME -> call
    | "FUNCTION" NAME ":" -> function
    | "DEC" NAME "#" SIGNED_INT -> dec
    | NAME "=" "&" NAME -> la
    | "GLOBAL" NAME ":" "#" SIGNED_INT ("=" "#" SIGNED_INT ("," "#" SIGNED_INT)*)? -> global
    | NAME "=" "PHI" "[" NAME "," NAME "]" ("," "[" NAME "," NAME "]")* -> phi

?relop : "<" -> lt
    | ">" -> gt
    | "<=" -> le
    | ">=" -> ge
    | "==" -> eq
    | "!=" -> ne
    
?binop: "+" -> add
    | "-" -> sub
    | "*" -> mul
    | "/" -> div
    | "%" -> rem
    | "<<" -> sll
    | ">>" -> sra
    | "&" -> and_
    | "|" -> or_
    | "^" -> xor

?unop : "-" -> neg
    | "+" -> pos
    
%import common.SIGNED_INT
%import common.WS
%import common.CPP_COMMENT
%import common.C_COMMENT

NAME: /[a-zA-Z\.\-_][a-zA-Z0-9\.\-_]*/ 

%ignore WS
%ignore CPP_COMMENT
%ignore C_COMMENT
""", parser = "earley")


this_module = sys.modules[__name__]


transformer = ast_utils.create_transformer(this_module, ToIR())


def parse(text):
    tree = parser.parse(text)
    return transformer.transform(tree)


def parse_file(filename):
    with open(filename) as f:
        return parse(f.read())

# -------------------------------- Interpreter --------------------------------#


class Environment:
    """ Environment contains all variables mapping and arrays. """

    def __init__(self) -> None:
        self.env = {}
        self.arrays: set[Array] = set()
        self.labels = {}

    def show(self):
        for k, v in self.env.items():
            print(f"{k}: {v}")

    def __getitem__(self, key: str) -> int | FunctionFrame:
        if key in self.env.keys():
            return self.env[key]
        else:
            if key in global_env.env.keys():
                return global_env[key]
            else:
                raise ValueError(f"Variable {key} is not defined.")

    def __setitem__(self, key: str, value: int | FunctionFrame) -> None:
        self.env[key] = value

    def load(self, address: int) -> int:
        """ Load value from address
        always find in global env
        """

        for array in global_env.arrays:
            if array.contain(address):
                return array.get(address)
        raise ValueError(f"address {address} not found in load")

    def store(self, address: int, src: Token) -> None:
        """ Store value to address"""
        value = self[src]
        assert isinstance(value, int), f"Value {value} is not an integer."
        for array in global_env.arrays:
            if array.contain(address):
                array.set(address, value)
                return
        raise ValueError(f"address {address} not found in store")


class Array:
    HEAD = 0x1000

    def __init__(self, start_address: int, size: int) -> None:
        self.start_address = start_address
        self.size = size
        self.values = [random.randint(1, 0xffff) for _ in range(size)]

    @staticmethod
    def new(size: int) -> int:
        start_address = Array.HEAD
        array = Array(start_address, size//4) # 4 bytes per int
        global_env.arrays.add(array)
        Array.HEAD += size
        return start_address

    def contain(self, address: int) -> bool:
        return address >= self.start_address and address < self.start_address + self.size * 4

    def get(self, address: int) -> int:
        return self.values[(address - self.start_address) // 4]

    def set(self, address: int, value: int) -> None:
        self.values[(address - self.start_address) // 4] = value


global_env = Environment()

# op2func maps an operator to a function
op2func = {
    # binary op
    BinOp.Add: lambda x, y: x + y,
    BinOp.Sub: lambda x, y: x - y,
    BinOp.Mul: lambda x, y: x * y,
    BinOp.Div: lambda x, y: int(x / y),
    BinOp.Rem: lambda x, y: x - int(x / y) * y,
    BinOp.Sll: lambda x, y: x << y,  # 左移
    BinOp.Sra: lambda x, y: x >> y,  # 算术右移
    BinOp.And: lambda x, y: x & y,
    BinOp.Or: lambda x, y: x | y,
    BinOp.Xor: lambda x, y: x ^ y,
    # relation op
    RelOp.Gt: lambda x, y: x > y,
    RelOp.Lt: lambda x, y: x < y,
    RelOp.Ge: lambda x, y: x >= y,
    RelOp.Le: lambda x, y: x <= y,
    RelOp.Eq: lambda x, y: x == y,
    RelOp.Ne: lambda x, y: x != y,
    # unary op
    UnOp.Neg: lambda x: -x,
    UnOp.Pos: lambda x: x,
}

step = 0

is_ssa = True

class FunctionFrame:
    def __init__(self, name: Token) -> None:
        self.name = name
        self.labels = {}
        self.codes = []
        self.env = Environment()
        self.trace = []
        self.current_label = None

    def new(self) -> FunctionFrame:
        new_frame = FunctionFrame(self.name)
        new_frame.codes = self.codes
        new_frame.labels = self.labels
        return new_frame

    def run(self, params: list[int] = []) -> int | None:
        """ Run the function with given params. """
        # current pc
        pc = 0
        # current stack
        args = []
        env = self.env
        while pc < len(self.codes):
            ir = self.codes[pc]
            pc += 1  # always increase pc
            global step
            step += 1
            if DEBUG:
                print(ir)
            # run the code and get the next pc
            match ir:
                case Binary(dst, left, op, right):
                    if op in op2func.keys():
                        env[dst] = op2func[op](env[left], env[right])
                    else:
                        raise NotImplementedError(
                            f"{op} is not implemented.")
                case Binaryi(dst, left, op, right):
                    if op in op2func.keys():
                        env[dst] = op2func[op](env[left], right)
                    else:
                        raise NotImplementedError(
                            f"{op} is not implemented.")
                case Unary(dst, op, right):
                    if op in op2func.keys():
                        env[dst] = op2func[op](env[right])
                    else:
                        raise NotImplementedError(
                            f"{op} is not implemented.")
                case Li(label, value):
                    env[label] = value
                # function definition and label is not code
                case Function(name) | Label(name):
                    global_env.labels[name] = pc
                    self.trace.append(name)
                case Goto(label):
                    if label not in self.labels:
                        raise ValueError(
                            f"Label {label} in function {self.name} is not defined.")
                    pc = self.labels[label]
                case Assign(dst, src):
                    env[dst] = env[src]
                case Return(src):
                    if src is None:  # void return
                        return None
                    value = env[src]
                    assert isinstance(value, int), f"Value {value} is not an integer."
                    return value
                case Arg(src):
                    args.append(env[src])
                case Param(dst):  # get the param from the stack
                    if len(params) == 0:
                        raise ValueError(
                            f"Function {self.name} needs more parameters.")
                    env[dst] = params.pop(0)
                case Call(dst, name):
                    if name == 'read':
                        res = int(input())
                        if dst is not None:
                            env[dst] = res
                    elif name == 'write':
                        print(args[0])
                        args = []  # reset args
                    else:
                        func_frame = env[name]
                        assert isinstance(func_frame, FunctionFrame), f"{func_frame} is not a function."
                        res = func_frame.new().run(args)
                        if dst is not None:
                            if res is not None:
                                env[dst] = res
                            else:
                                env[dst] = random.randint(1, 0xffff)
                        args = []  # reset args
                case If(left, op, right, label):
                    if op in op2func.keys():
                        if op2func[op](env[left], env[right]) == 1:
                            pc = self.labels[label]
                    else:
                        raise NotImplementedError(
                            f"{op} in relop is not implemented.")
                case Dec(dst, size):
                    env[dst] = Array.new(size)
                case Store(dst, offset, src):  # * ( x + # k ) = y
                    address = env[dst]
                    assert isinstance(address, int), f"Address {address} is not an integer."
                    env.store(address + offset, src)
                case Deref(dst, src, offset):  # x = * ( y + # k )
                    address = env[src]
                    assert isinstance(address, int), f"Address {address} is not an integer."
                    value = env.load(address + offset)
                    env[dst] = value
                case La(dst, label):
                    if label not in global_env.labels:
                        raise ValueError(
                            f"Label {label} in function {self.name} is not defined.")
                    env[dst] = global_env.labels[label]
                case Phi(dst, srcs):
                    assert is_ssa, "Phi node is not in SSA form"
                    assert len(self.trace) > 1, "No previous block"
                    src = srcs[self.trace[-2]]
                    env[dst] = env[src]
                case _:
                    raise NotImplementedError(f"{ir} is not implemented.")
        assert False, f"No return statement in function {self.name}."

    def add_code(self, code) -> None:
        if isinstance(code, Label):
            self.labels[code.label] = len(self.codes)
        self.codes.append(code)

    def __str__(self) -> str:
        codes = [f"{self.codes[0]}:"]
        for code in self.codes[1:]:
            codes.append(f"    {code}")
        return "\n".join(codes)


def build_function(irs: list[IRNode]) -> list[FunctionFrame]:
    frames = []
    global_var: dict[str, list[int]] = {}
    def_vars = set()
    is_block_entry = False
    have_phi = False
    global is_ssa
    if len(irs) == 0 or not (isinstance(irs[0], Function) or isinstance(irs[0], Global)):
        raise SyntaxError("IR should start with a FUNCTION or GLOBAL.")
    for ir in irs:
        if ir.dst_var is not None:
            if ir.dst_var in def_vars:
                is_ssa = False
                if have_phi:
                    raise SyntaxError(f"Phi node is not in SSA form. {ir.dst_var} redefined.")
            def_vars.add(ir.dst_var)
        if isinstance(ir, Function):
            frame = FunctionFrame(ir.name)
            frames.append(frame)
            global_env[ir.name] = frame
            frames[-1].add_code(ir)
            is_block_entry = True
            def_vars.clear()
        elif isinstance(ir, Global):
            if frames:
                raise SyntaxError("Global variable should be defined before function.")
            global_var[ir.name] = ir.values
        elif isinstance(ir, Label):
            is_block_entry = True
            if not frames:
                raise SyntaxError("Cannot define instruction outside of a function.")
            frames[-1].add_code(ir)
        elif isinstance(ir, Phi):
            if not is_block_entry:
                raise SyntaxError("Phi node should be the first instruction in a block.")
            if not is_ssa:
                raise SyntaxError("Phi node is not in SSA form.")
            if not frames:
                raise SyntaxError("Cannot define instruction outside of a function.")
            frames[-1].add_code(ir)
            have_phi = True
        else:
            is_block_entry = False
            if not frames:
                raise SyntaxError("Cannot define instruction outside of a function.")
            frames[-1].add_code(ir)
    for name, values in global_var.items():
        address = Array.new(len(values) * 4)
        for array in global_env.arrays:
            if array.contain(address):
                for i, value in enumerate(values):
                    array.set(address + i * 4, value)
                break
        global_env.labels[name] = address
    return frames


def run(irs: list[IRNode], check_ssa: bool = False) -> int | None:
    """
    Runs the given IRNodes in the given environment.
    """
    all_functions = build_function(irs)
    if check_ssa and not is_ssa:
        raise SyntaxError("IR is not in SSA form.")
    if DEBUG:
        [print(frame) for frame in all_functions]
        print("\033[31m")
        print("If IRs are not correctly parsed, please contact to TA asap.")
        print("\033[0m")
    if "main" not in global_env.env.keys():
        raise SyntaxError("No main function.")
    main = global_env["main"]
    assert isinstance(main, FunctionFrame), "Main is not a function."
    return_value = main.run()
    return return_value


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(
        description="Interpret file generated by your compiler.")
    arg_parser.add_argument("file", type=str, help="The IR file to interpret.")
    arg_parser.add_argument("-d", "--debug", action="store_true",
                            help="Whether to print debug info.")
    arg_parser.add_argument("-s", "--ssa", "--check-ssa", action="store_true",
                            help="Whether to check SSA form.")
    args = arg_parser.parse_args()
    if args.debug:
        print("Debug mode on.")
        DEBUG = True
    irs = parse_file(args.file)
    return_value = run(irs, check_ssa=args.ssa)
    # 0 green, else red
    colored_return_value = f"\033[1;32m{return_value}\033[0m" if return_value == 0 else f"\033[1;31m{return_value}\033[0m"
    print(f'Exit with code {colored_return_value} within {step} steps.')
    exit(return_value)
