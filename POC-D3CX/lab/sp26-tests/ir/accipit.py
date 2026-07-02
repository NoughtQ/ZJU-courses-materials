from __future__ import annotations
from lark import Lark, Transformer, ast_utils, Token, UnexpectedInput, v_args
from lark.ast_utils import Ast
from dataclasses import dataclass
from typing import Union, Any
import random

import sys
import argparse

sys.setrecursionlimit(50000)  # 加深调用栈深度，因为python没有尾递归优化


class SemanticError(Exception):
    def __init__(self, message):
        super().__init__(message)


STEP = 0
DEBUG = False


class IRNode():
    reduced_msg = ""
    line: int | None = None

    def method_wrapper(self, func, step: int):
        def wrapper(*args, **kwargs):
            name = self.__str__().split('\n')[0].strip().rstrip("{").strip()
            prefix = f"STEP {step}.".ljust(10)
            if isinstance(self, tuple([ValueBinding, Terminator, FunDefn])):
                line = f" \033[38;5;214m< Line {self.line} > \033[0m"
                print(
                    f"\n{prefix} \033[1;32mEval\033[0m   {name} {line}")
            if isinstance(self, FunDefn):
                args_string = f"({ ', '.join(f'{param[0]}: {arg}' for param, arg in zip(self.params.params, args[0])) })"
                print(
                    f"{prefix} \033[1;36mSimp\033[0m   fn {self.name} {args_string} -> {self.ret}")
            result = func(*args, **kwargs)
            if isinstance(self, tuple([ValueBinding, Ret])) and self.reduced_msg:
                print(f"{prefix} \033[1;36mSimp\033[0m   {self.reduced_msg}")
            if isinstance(self, ValueBinding):
                print(
                    f"{prefix} \033[1;33mBind   {'Unit' if result is None else result}\033[0m to {self.name}")
            if isinstance(self, FunDefn):
                print(f"{prefix} \033[1;33mReturn {result}\033[0m for {name}")
            return result
        return wrapper

    def __getattribute__(self, name):
        obj = super().__getattribute__(name)
        if name == "eval" and isinstance(self, tuple([ValueBinding, Terminator, FunDefn])):
            global STEP
            step = STEP
            STEP = STEP + 1
            if DEBUG and callable(obj):
                return self.method_wrapper(obj, step)
        return obj

    def __str__(self):
        return self.__class__.__name__ + " " + ", ".join(f"{attr}" for key, attr in self.__dict__.items() if key not in ["reduced_msg", "line"]) + " "


@dataclass
class IntConst(Ast):
    value: int

    def __str__(self):
        return str(self.value)

    def eval(self) -> int:
        return self.value


@dataclass
class NoneConst():
    def eval(self):
        return 1


@dataclass
class UnitConst():
    def eval(self) -> UnitConst:
        return self


@dataclass
class Ident(IRNode):
    name: str

    def __str__(self):
        return self.name

    def eval(self) -> Any:
        return env.get(self)


Value = Union[IntConst, NoneConst, UnitConst, Ident]


class I32(IRNode):
    def __str__(self):
        return "i32"


class Unit(IRNode):
    def __str__(self):
        return "()"


@dataclass
class Pointer(IRNode):
    name: str


@dataclass
class FunType(IRNode):
    params: list[Token]
    ret: Token

    def __str__(self):
        return f"fn ({', '.join(str(param) for param in self.params)}) -> {self.ret}"


Type = Union[I32, Unit, Pointer, FunType]


@dataclass
class Ptr(IRNode):
    addr: int

    def __str__(self):
        return f"0x{self.addr * 4:08X}"


class Environment():
    def __init__(self):
        self.global_env: dict[str, Any] = {}
        self.frames: list[dict[str, Any]] = []
        self.memory: list[int] = [
            random.randint(1, 0xffff) for _ in range(1024)]
        self.capacity: int = 1024
        self.size: int = 0
        self.trace: list[Ident] = []
        self._trace_entry: list[int] = []

    def push_trace(self, label: Ident):
        self.trace.append(label)
    
    def rollback_trace(self):
        while len(self.trace) > self._trace_entry[-1]:
            self.trace.pop()
        self._trace_entry.pop()

    def push_frame(self):
        self.frames.append({})
        env._trace_entry.append(len(env.trace))

    def pop_frame(self):
        self.frames.pop()
        self.rollback_trace()

    def allocate(self, size: int, init: list[int] = []) -> Ptr:
        if self.size + size > self.capacity:
            size_lacked = self.size + size - self.capacity
            size_to_extend = (size_lacked + 1023) // 1024 * 1024
            self.memory.extend([
                random.randint(1, 0xffff) for _ in range(size_to_extend)])
            self.capacity += size_to_extend
        addr = self.size
        self.size += size
        if init:
            self.memory[addr:addr+size] = init
        return Ptr(addr)

    def add_global(self, name, value: Any):
        name = name.__str__()
        if name in self.global_env:
            raise SemanticError(f"Global identifier {name} is defined twice.")
        self.global_env[name] = value

    def get_global(self, name) -> Any:
        return self.global_env.get(name.__str__())

    def add_local(self, name, value: Any):
        name = name.__str__()
        self.frames[-1][name] = value

    def get_local(self, name) -> Any:
        return self.frames[-1].get(name.__str__())

    def get(self, name: Ident) -> Any:
        if name.name.startswith("@"):
            return self.get_global(name)
        else:
            return self.get_local(name)

    def store(self, ptr: Ptr, value: int):
        if ptr is None:
            raise SemanticError(f"{name} is not defined.")
        if not isinstance(ptr, Ptr):
            raise SemanticError(f"{name} is not a pointer.")
        self.memory[ptr.addr] = value

    def load(self, ptr: Ptr) -> int:
        if ptr is None:
            raise SemanticError(f"{name} is not defined.")
        if not isinstance(ptr, Ptr):
            raise SemanticError(f"{name} is not a pointer.")
        return self.memory[ptr.addr]

    def clear(self):
        self.global_env.clear()
        self.frames.clear()


env = Environment()


@dataclass
class BinExpr(IRNode, Ast):
    binop: Token
    v1: IntConst | Ident
    v2: IntConst | Ident

    def eval(self):
        v1 = self.v1.eval()
        v2 = self.v2.eval()
        self.reduced_msg = f"BinExpr {self.binop}, {v1}, {v2}"
        if self.binop == "add":
            return v1 + v2
        elif self.binop == "sub":
            return v1 - v2
        elif self.binop == "mul":
            return v1 * v2
        elif self.binop == "div":
            return int(v1 / v2)
        elif self.binop == "rem":
            return v1 - int(v1 / v2) * v2
        elif self.binop == "and":
            return v1 & v2
        elif self.binop == "or":
            return v1 | v2
        elif self.binop == "xor":
            return v1 ^ v2
        elif self.binop == "eq":
            return v1 == v2
        elif self.binop == "ne":
            return v1 != v2
        elif self.binop == "lt":
            return v1 < v2
        elif self.binop == "le":
            return v1 <= v2
        elif self.binop == "gt":
            return v1 > v2
        elif self.binop == "ge":
            return v1 >= v2
        else:
            raise SemanticError(f"Unknown binop {self.binop}")


@dataclass
class Alloca(IRNode, Ast):
    tpe: Type
    size: IntConst

    def eval(self) -> Ptr:
        return env.allocate(self.size.eval())


@dataclass
class Load(IRNode, Ast):
    name: Ident

    def eval(self):
        addr = self.name.eval()
        self.reduced_msg = f"Load {addr}"
        return env.load(addr)


@dataclass
class Store(IRNode, Ast):
    value: Ident
    name: Ident

    def eval(self):
        addr = self.name.eval()
        v = self.value.eval()
        self.reduced_msg = f"Store {v}, {addr}"
        env.store(addr, v)


@dataclass
class Gep(IRNode):
    tpe: Type
    name: Ident
    offsets: list[tuple[IntConst, Union[IntConst, NoneConst]]]

    def __str__(self):
        indexing = ", ".join(f"{idx} < {dim}" for idx, dim in self.offsets)
        return f"offset {self.tpe}, {self.name}, {indexing}"

    def eval(self) -> Ptr:
        dims_imm = []
        idxes_imm = []
        addr = self.name.eval().addr
        offset_addr = 0
        for idx, dim in self.offsets:
            dims_imm.append(dim.eval())
            idxes_imm.append(idx.eval())
            offset_addr = offset_addr * dims_imm[-1] + idxes_imm[-1]
        indexing = ", ".join(f"{idx} < {dim}" for idx,
                             dim in zip(idxes_imm, dims_imm))
        self.reduced_msg = f"offset {self.tpe}, 0x{addr * 4 :08X}, {indexing}"
        return Ptr(addr + offset_addr)


@dataclass
class Fncall(IRNode):
    name: Ident
    args: list[Value]

    def __str__(self):
        return f"call {self.name} ({', '.join(str(arg) for arg in self.args)})"

    def eval(self):
        if self.name.__str__() == "@write":
            print(self.args[0].eval())
            return 0
        elif self.name.__str__() == "@read":
            return int(input())
        fun = env.get_global(self.name)
        if not isinstance(fun, FunDefn) and not isinstance(fun, FunDecl):
            raise SemanticError(f"{self.name} is not a function.")
        values = [value.eval() for value in self.args]
        return fun.eval(values)


ValueBindingOp = Union[BinExpr, Gep, Fncall, Alloca, Load, Store]


@dataclass
class ValueBinding(IRNode):
    name: Ident
    op: ValueBindingOp
    line: int | None = None

    def __str__(self):
        return f"let {self.name} = {self.op}"

    def eval(self):
        value = self.op.eval()
        if self.op.reduced_msg:
            self.reduced_msg = f"let {self.name} = {self.op.reduced_msg}"
        env.add_local(self.name, value)
        return value


@dataclass
class Br(IRNode, Ast):
    cond: Value
    label1: Ident
    label2: Ident
    line: int | None = None

    def eval(self) -> int:
        target = self.label1 if self.cond.eval() else self.label2
        return target.eval().eval()


@dataclass
class Jmp(IRNode, Ast):
    label: Ident
    line: int | None = None

    def eval(self) -> int:
        return self.label.eval().eval()


@dataclass
class Ret(IRNode):
    value: IntConst | Ident | UnitConst
    line: int | None = None

    def eval(self) -> Value:
        res = self.value.eval()
        self.reduced_msg = f"Ret {res}"
        return res


Terminator = Union[Br, Jmp, Ret]


@dataclass
class PList(IRNode):
    params: list[tuple[Ident, Type]]

    def __str__(self):
        return "(" + ", ".join(f"{name}: {tpe}" for name, tpe in self.params) + ")"

    def eval(self, values):
        env.push_frame()
        for (name, _), value in zip(self.params, values):
            env.add_local(name, value)


@dataclass
class BasicBlock(IRNode):
    label: Ident
    insts: list[ValueBinding | Terminator]

    def __str__(self):
        return f"{self.label}:\n" + "\n".join(str(inst) for inst in self.insts)

    def eval(self) -> int | UnitConst:
        env.push_trace(self.label)
        for idx, inst in enumerate(self.insts):
            if isinstance(inst, ValueBinding):
                inst.eval()
            else:
                if idx != len(self.insts) - 1:
                    raise SemanticError(
                        f"Terminator instruction {inst} is not the last instruction in block {self.label}.")
                return inst.eval()


@dataclass
class Body(IRNode):
    bbs: list[BasicBlock]

    def __str__(self):
        return "{\n" + "\n".join(str(bb) for bb in self.bbs) + "\n}"

    def eval(self) -> int:
        return self.bbs[0].eval()


class GlobalDecl:
    name: Ident
    tpe: Type
    size: IntConst
    values: list[IntConst]

    def __init__(self, name: Ident, tpe: Type, size: IntConst, values: list[IntConst]):
        self.name = name
        self.tpe = tpe
        self.size = size
        self.values = values
        if values and len(values) != size.eval():
            raise SemanticError(
                f"Global array {name} has size {size} but {len(values)} values are provided.")
        elif values:
            ptr = env.allocate(size.eval(), [value.eval() for value in values])
        else:
            ptr = env.allocate(size.eval(), [0 for _ in range(size.eval())])
        env.add_global(name, ptr)

    def __str__(self):
        if self.values:
            return f"{self.name} : {self.tpe}, {self.size} = [{', '.join(str(value) for value in self.values)}]"
        else:
            return f"{self.name} : {self.tpe}, {self.size}"


@dataclass
class Phi:
    srcs: list[tuple[Ident, Ident]]
    line: int | None = None

    def __str__(self):
        return "phi [" + ", ".join(f"{src[0]}, {src[1]}" for src in self.srcs) + "]"

    def eval(self) -> Ident:
        if len(env.trace) < 2:
            raise SemanticError(
                "No previous label found for Phi instruction.")
        label = env.trace[-2]
        self.reduced_msg = f"Phi {''.join(f'[{src[0]}, {src[1].eval()}]' for src in self.srcs)} with {label} as the previous label."
        for src in self.srcs:
            if src[0] == label:
                return src[1].eval()
        raise SemanticError(
            f"Phi instruction {self} has no matching source for label {label}.")


class FunDefn(IRNode, Ast):
    name: Ident
    params: PList
    ret: Type
    body: Body

    def __init__(self, name: Ident, params: PList, ret: Type, body: Body, line: int):
        self.name = name
        self.params = params
        self.ret = ret
        self.body = body
        self.line = line
        env.add_global(name, self)

    def __str__(self):
        return f"fn {self.name} {self.params} -> {self.ret} {self.body}"

    def eval(self, args) -> int:
        self.params.eval(args)
        for bb in self.body.bbs:
            env.add_local(bb.label, bb)
        return_value = self.body.eval()
        env.pop_frame()
        return return_value


class FunDecl(IRNode, Ast):
    name: Ident
    params: PList
    ret: Type

    def __init__(self, name: Ident, params: PList, ret: Type, line: int):
        self.name = name
        self.params = params
        self.ret = ret
        self.line = line
        env.add_global(name, self)

    def __str__(self):
        return f"fn {self.name} ({self.params}) -> {self.ret};"


Decl = Union[GlobalDecl, FunDefn, FunDecl]


@dataclass
class Program():
    decls: list[Decl]

    def __str__(self):
        return "\n".join(str(decl) for decl in self.decls)


class BaseTransformer(Transformer):
    def name(self, children): return "".join(children)
    def i32(self, _token): return I32()
    def unit(self, _token): return Unit()
    def int_const(self, n): return IntConst(int(n[0]))

    def none_const(self, token): return NoneConst()

    def unit_const(self, _token): return UnitConst()

    def SIGNED_INT(self, n): return int(n)
    def function_type(self, items): return FunType(items[:-1], items[-1])
    def pointer(self, items): return Pointer(items[0].__str__() + "*")
    def ident(self, items): return Ident(items[0] + items[1])
    def gep(self, items): return Gep(items[0], items[1], [
        (items[i], items[i+1]) for i in range(2, len(items), 2)])

    def fncall(self, items): return Fncall(items[0], items[1:])

    @v_args(meta=True)
    def value_binding_untyped(
            self, meta, items):
        return ValueBinding(items[0], items[1], meta.line)

    @v_args(meta=True)
    def value_binding_typed(
        self, meta, items): return ValueBinding(items[0], items[2], meta.line)

    @v_args(meta=True)
    def ret(self, meta, items): return Ret(items[0], meta.line)

    @v_args(meta=True)
    def jp(self, meta, items): return Jmp(items[0], meta.line)

    @v_args(meta=True)
    def branch(self, meta, items): return Br(
        items[0], items[1], items[2], meta.line)

    def plist(self, items): return PList(
        [(items[i], items[i+1]) for i in range(0, len(items), 2)])

    def bb(self, items): return BasicBlock(items[0], items[1:])
    def body(self, items): return Body(items)

    def global_decl(self, items): return GlobalDecl(
        items[0], items[1], items[2], items[3:])

    @v_args(meta=True)
    def phi(self, meta, items):
        srcs = [(items[i], items[i+1]) for i in range(0, len(items), 2)]
        return Phi(srcs, meta.line)

    @v_args(meta=True)
    def fn_defn(self, meta, items): return FunDefn(
        items[0], items[1], items[2], items[3], meta.line)

    @v_args(meta=True)
    def fn_decl(self, meta, items): return FunDecl(
        items[0], items[1], items[2], meta.line)

    def program(self, items): return Program(items)


accipit_grammar = """
    ?start : program

    name : /[a-zA-Z._-][a-zA-Z0-9._-]*/
    ident : /@/ (name | INT)
    | /#/ (name | INT)
    | /%/ (name | INT)

    int_const : SIGNED_INT -> int_const
    none_const : "none"
    unit_const : "()"
    ?const : int_const | none_const | unit_const

    ?value : ident | const

    type : /i32/ -> i32
    | "()" -> unit
    | type "*" -> pointer
    | "fn" "(" (type ("," type)*)? ")" "->"  type -> function_type

    value_binding_untyped : "let" ident "=" (bin_expr | gep | fncall | alloca | load | store | phi)
    value_binding_typed : "let" ident ":" type "=" (bin_expr | gep | fncall | alloca | load | store)
    ?value_binding : value_binding_untyped | value_binding_typed
    ?terminator : branch | jp | ret

    ?binop : /add/ | /sub/ | /mul/ | /div/ | /rem/ | /and/ | /or/ | /xor/ | /eq/ | /ne/ | /lt/ | /le/ | /gt/ | /ge/
    bin_expr : binop value "," value
    alloca : "alloca" type "," int_const
    load : "load" ident
    phi: "phi" "[" ident "," ident"]" ("," "[" ident "," ident "]")*
    store : "store" value "," ident
    gep : "offset" type "," ident ( "," "[" value "<" (int_const | none_const) "]" )+
    fncall : "call" ident ("," value)*

    branch : "br" value "," "label" ident "," "label" ident
    jp : "jmp" "label" ident
    ret : "ret" value

    ?plist : (ident ":" type ("," ident ":" type)*)?
    ?label : ident ":"
    ?bb : label (value_binding| terminator)+
    body : "{" bb* "}"

    global_decl : ident ":" "region" type "," int_const ("=" "[" value ("," value)* "]")?
    fn_defn : "fn" ident "(" plist ")" "->" type body
    fn_decl : "fn" ident "(" plist ")" "->" type ";"
    program : (global_decl | fn_defn | fn_decl)*

    %import common.WS
    %import common.CPP_COMMENT
    %import common.C_COMMENT
    %import common.INT
    %import common.SIGNED_INT

    %ignore WS
    %ignore CPP_COMMENT
    %ignore C_COMMENT
"""
# We can not name rule branch to br, as there seems to be name collision?

this_module = sys.modules[__name__]
accipit_transformer = ast_utils.create_transformer(
    this_module, BaseTransformer())
parser = Lark(accipit_grammar, propagate_positions=True)


def parse(file: str) -> Program:
    with open(file) as f:
        text = f.read()
    try:
        ast = parser.parse(text)
        result: Program = accipit_transformer.transform(ast)
        return result
    except UnexpectedInput as e:
        print(e.get_context(text))
        print(f"Syntax error at position {e.column}: {e}")
        exit(1)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(
        description="Interpreter for Accipit IR")
    arg_parser.add_argument("file", type=str, help="the IR file to interpret.")
    arg_parser.add_argument(
        "-d", "--debug", action="store_true", help="whether to print debug info.")
    args = arg_parser.parse_args()
    program = parse(args.file)
    if args.debug:
        DEBUG = True
        print(f"The parsed AST is:\n{program}")
        print("\n-----------------The evaluation starts here-----------------\n")
    main = env.global_env.get("@main")
    if main is None or not isinstance(main, FunDefn):
        raise SemanticError("Main function is not defined.")
    return_value = main.eval([UnitConst])
    colored_return_value = f"\033[1;32m{return_value}\033[0m" if return_value == 0 else f"\033[1;31m{return_value}\033[0m"
    print(f'Exit with code {colored_return_value} within {STEP} steps.')
    exit(return_value)
