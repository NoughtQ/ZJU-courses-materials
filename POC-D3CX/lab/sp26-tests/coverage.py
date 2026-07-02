import argparse

from lark import Lark, UnexpectedInput, Visitor, Tree, Token


text_parser = Lark("""
comp_unit   : [comp_unit] decl
            | [comp_unit] func_def

decl        : var_decl
b_type      : "int"
var_decl    : b_type var_def ("," var_def)* ";"
var_def     : IDENT ("[" INTCONST "]")*
            | IDENT ("[" INTCONST "]")* "=" init_val
init_val    : exp | "{" [init_val("," init_val)*] "}"

func_def    : func_type IDENT "(" [func_f_params] ")" block
func_type   : b_type | "void"
func_f_params: func_f_param ("," func_f_param)*
func_f_param: b_type IDENT ["[" "]" ("[" INTCONST "]")*]

block       : "{" block_item* "}"
block_item  : decl | stmt
stmt        : l_val "=" exp ";"
            | [exp] ";"
            | block
            | "if" "(" cond ")" stmt ["else" stmt]
            | "while" "(" cond ")" stmt
            | RETURN [exp] ";"

exp         : add_exp
cond        : l_or_exp
l_val       : IDENT ("[" exp "]")*
primary_exp : "(" exp ")" | l_val | number
number      : INTCONST
unary_exp   : primary_exp | unary_op unary_exp | IDENT "(" [func_r_params] ")"
unary_op    : "+" | "-" | "!"
func_r_params: exp ("," exp)*

mul_exp     : unary_exp | mul_exp mul_op unary_exp
mul_op      : "*" | "/" | "%"
add_exp     : mul_exp  | add_exp add_op mul_exp
add_op      : "+" | "-"

rel_exp     : add_exp | rel_exp rel_op add_exp
rel_op      : "<" | ">" | "<=" | ">="
eq_exp      : rel_exp | eq_exp eq_op rel_exp
eq_op       : "==" | "!="
l_and_exp   : eq_exp | l_and_exp "&&" eq_exp
l_or_exp    : l_and_exp | l_or_exp "||" l_and_exp

IDENT.1: /[a-zA-Z_][a-zA-Z0-9_]*/
INTCONST: /0[xX][0-9a-fA-F]+|0[0-7]*|[1-9][0-9]*/
RETURN.2: "return"

%import common.WS
%import common.CPP_COMMENT
%import common.C_COMMENT

%ignore WS
%ignore CPP_COMMENT
%ignore C_COMMENT
""", parser="earley", propagate_positions=True, start='comp_unit', keep_all_tokens=True)


def green_background(text):
    return '\033[42m' + text + '\033[0m'


def red(text):
    return '\033[91m' + text + '\033[0m'


def green(text):
    return '\033[92m' + text + '\033[0m'


def get_all_tokens(tree: Tree):
    all_tokens = tree.scan_values(lambda v: isinstance(v, Token))
    return list(all_tokens)


def get_all_rules(tree: Tree):
    def _get_all_rules(tree: Tree):
        if tree.data.type == 'RULE':
            yield tree.data.value
        for child in tree.children:
            if isinstance(child, Tree):
                yield from _get_all_rules(child)
    return list(_get_all_rules(tree))


class Expansion:
    def __init__(self, text: str, optional=True):
        self.text = text
        if self.text.find('[') == -1:
            self.is_optional = False
        else:
            self.is_optional = True and optional
        if self.text.find('{') == -1:
            self.is_repeat = False
        else:
            self.is_repeat = True
        self.is_covered = False
        self.is_optional_covered = False
        self.is_repeat_covered = False

    def full_coverage(self) -> bool:
        repeat = (not self.is_repeat) or self.is_repeat_covered
        optional = (not self.is_optional) or self.is_optional_covered
        return self.is_covered and repeat and optional

    def __repr__(self) -> str:
        return f"Expansion({self.text})\n is_covered: {self.is_covered}\n is_optional: {self.is_optional}  is_optional_covered: {self.is_optional_covered}\n is_repeat  : {self.is_repeat}  is_repeat_covered: {self.is_repeat_covered}\n"

    def __str__(self) -> str:
        return self.text


class Rule:
    def __init__(self, name, expansions: list[Expansion]):
        self.name = name
        self.expansions = expansions

    def full_coverage(self) -> bool:
        return all(map(lambda x: x.full_coverage(), self.expansions))

    def __repr__(self) -> str:
        expansions = list(
            map(repr, filter(lambda x: not x.full_coverage(), self.expansions)))
        return f"Rule({self.name})\n" + ''.join(expansions) + '\n'

    # A ::= B
    #   | C
    #   | D
    def __str__(self):
        expansions = list(
            map(str, filter(lambda x: not x.full_coverage(), self.expansions)))
        first = expansions[0]
        rest = expansions[1:]
        rest = map(lambda x: f'{" " * 18}| {x}', rest)
        return f"{self.name:<15} ::= {first}\n" + '\n'.join(rest) + '\n'


RULES = {
    'comp_unit': Rule("CompUnit", [
        Expansion('[CompUnit] Decl'),
        Expansion('[CompUnit] FuncDef',),
    ]),

    'decl': Rule("Decl", [Expansion('VarDecl')]),
    'b_type': Rule("BType", [Expansion('"int"')]),
    'var_decl': Rule("VarDecl", [
        Expansion('BType VarDef {"," VarDef} ";"')
    ]),
    'var_def': Rule("VarDef", [
        Expansion('IDENT {"[" INTCONST "]"}', optional=False),
        Expansion('IDENT {"[" INTCONST "]"} "=" InitVal', optional=False),
    ]),
    'init_val': Rule("InitVal", [
        Expansion('Exp'),
        Expansion('"{", InitVal {"," InitVal} "}"'),
    ]),

    'func_def': Rule("FuncDef", [
        Expansion('FuncType IDENT "(" [FuncFParams] ")" Block'),
    ]),
    'func_type': Rule("FuncType", [
        Expansion('"void"'),
        Expansion('int')
    ]),
    'func_f_params': Rule("FuncFParams", [
        Expansion('FuncFParam {"," FuncFParam}'),
    ]),
    'func_f_param': Rule("FuncFParam", [
        Expansion('BType IDENT ["[" "]" {"[" INTCONST "]"}]'),
    ]),

    'block': Rule("Block", [
        Expansion('"{", {BlockItem}, "}"'),
    ]),
    'block_item': Rule("BlockItem", [
        Expansion('Decl'),
        Expansion('Stmt'),
    ]),
    'stmt': Rule("Stmt", [
        Expansion('LVal "=" Exp ";"'),
        Expansion('[Exp] ";"'),
        Expansion('Block'),
        Expansion('IF "(" Cond ")" Stmt [ELSE Stmt]'),
        Expansion('WHILE "(" Cond ")" Stmt'),
        Expansion('return [Exp] ";"'),
    ]
    ),

    'exp': Rule("Exp", [Expansion('AddExp')]),
    'cond': Rule("Cond", [Expansion('LOrExp')]),
    'l_val': Rule("LVal", [Expansion('IDENT {"[" Exp "]"}', optional=False)]),
    'primary_exp': Rule("PrimaryExp", [
        Expansion(' "(" Exp ")"'),
        Expansion('LVal'),
        Expansion('Number'),
    ]),
    'number': Rule("Number", [Expansion('INTCONST')]),
    'unary_exp': Rule("UnaryExp", [
        Expansion('PrimaryExp'),
        Expansion('IDENT "(" [FuncRParams] ")"'),
        Expansion('UnaryOp UnaryExp'),
    ]),
    'unary_op': Rule("UnaryOp", [
        Expansion('"+"'),
        Expansion('"-"'),
        Expansion('"!"'),
    ]),
    'func_r_params': Rule("FuncRParams", [
        Expansion('Exp {"," Exp}'),
    ]),

    'mul_exp': Rule("MulExp", [
        Expansion('UnaryExp'),
        Expansion('MulExp MulOp UnaryExp'),
    ]),
    'mul_op': Rule("MulOp", [
        Expansion('"*"'),
        Expansion('"/"'),
        Expansion('"%"'),
    ]),
    'add_exp': Rule("AddExp", [
        Expansion('MulExp'),
        Expansion('AddExp AddOp MulExp'),
    ]),
    'add_op': Rule("AddOp", [
        Expansion('"+"'),
        Expansion('"-"'),
    ]),
    'rel_exp': Rule("RelExp", [
        Expansion('AddExp'),
        Expansion('RelExp RelOp AddExp'),
    ]),
    'rel_op': Rule("RelOp", [
        Expansion('"<"'),
        Expansion('"<="'),
        Expansion('">"'),
        Expansion('">="'),
    ]),
    'eq_exp': Rule("EqExp", [
        Expansion('RelExp'),
        Expansion('EqExp EqOp RelExp'),
    ]),
    'eq_op': Rule("EqOp", [
        Expansion('"=="'),
        Expansion('"!="'),
    ]),
    'l_and_exp': Rule("LAndExp", [
        Expansion('EqExp'),
        Expansion('LAndExp "&&" EqExp'),
    ]),
    'l_or_exp': Rule("LOrExp", [
        Expansion('LAndExp'),
        Expansion('LOrExp "||" LAndExp'),
    ]),
}


class CoverageVisitor(Visitor):
    def comp_unit(self, tree: Tree):
        type = tree.children[1].data.value
        match type:
            case 'decl':
                RULES['comp_unit'].expansions[0].is_covered = True
                RULES['comp_unit'].expansions[0].is_optional_covered = True
            case 'func_def':
                RULES['comp_unit'].expansions[1].is_covered = True
                RULES['comp_unit'].expansions[1].is_optional_covered = True

    def decl(self, tree: Tree):
        RULES['decl'].expansions[0].is_covered = True

    def b_type(self, tree: Tree):
        RULES['b_type'].expansions[0].is_covered = True

    def var_decl(self, tree: Tree):
        RULES['var_decl'].expansions[0].is_covered = True
        if len(tree.children) > 3:
            RULES['var_decl'].expansions[0].is_repeat_covered = True

    def var_def(self, tree: Tree):
        tokens = get_all_tokens(tree)
        is_array = tokens.count('[') >= 1
        rules = get_all_rules(tree)
        if rules.count('init_val') >= 1:
            RULES['var_def'].expansions[1].is_covered = True
            if is_array:
                RULES['var_def'].expansions[1].is_repeat_covered = True
        else:
            RULES['var_def'].expansions[0].is_covered = True
            if is_array:
                RULES['var_def'].expansions[0].is_repeat_covered = True

    def init_val(self, tree: Tree):
        if isinstance(tree.children[0], Token):  # token '{'
            RULES['init_val'].expansions[1].is_covered = True
            RULES['init_val'].expansions[1].is_repeat_covered = True
            if len(get_all_tokens(tree)) == 2:
                RULES['init_val'].expansions[1].is_optional_covered = True
        else:
            RULES['init_val'].expansions[0].is_covered = True

    def func_def(self, tree: Tree):
        RULES['func_def'].expansions[0].is_covered = True
        rules = get_all_rules(tree)
        if rules.count('func_f_params') == 0:
            RULES['func_def'].expansions[0].is_optional_covered = True

    def func_type(self, tree: Tree):
        if isinstance(tree.children[0], Token):  # token 'void'
            RULES['func_type'].expansions[0].is_covered = True
        else:  # b_type
            RULES['func_type'].expansions[1].is_covered = True

    def func_f_params(self, tree: Tree):
        RULES['func_f_params'].expansions[0].is_covered = True
        rules = get_all_rules(tree)
        if rules.count("func_f_param") >= 2:
            RULES['func_f_params'].expansions[0].is_repeat_covered = True

    def func_f_param(self, tree: Tree):
        RULES['func_f_param'].expansions[0].is_covered = True
        tokens = get_all_tokens(tree)
        if tokens.count('[') >= 1:
            RULES['func_f_param'].expansions[0].is_optional_covered = True
        if tokens.count('[') >= 2:
            RULES['func_f_param'].expansions[0].is_repeat_covered = True

    def block(self, tree: Tree):
        RULES['block'].expansions[0].is_covered = True
        rules = get_all_rules(tree)
        if rules.count('block_item') > 1:
            RULES['block'].expansions[0].is_repeat_covered = True

    def block_item(self, tree: Tree):
        type = tree.children[0].data.value
        match type:
            case 'decl':
                RULES['block_item'].expansions[0].is_covered = True
            case 'stmt':
                RULES['block_item'].expansions[1].is_covered = True
            case _:
                raise Exception(f"Unknown block_item type {type}")

    def stmt(self, tree: Tree):
        rules = get_all_rules(tree)
        if len(rules) == 1:
            if tree.children[0] == None:
                RULES['stmt'].expansions[1].is_optional_covered = True
                return
            type = tree.children[0].value
            match type:
                case 'return':  # empty return
                    RULES['stmt'].expansions[5].is_optional_covered = True
                case _:
                    raise Exception(f"Unknown stmt type {rules}")
            return
        if isinstance(tree.children[0], Token):
            type = tree.children[0].value
        else:
            type = tree.children[0].data
        match type:
            case 'l_val':
                RULES['stmt'].expansions[0].is_covered = True
            case 'exp':
                RULES['stmt'].expansions[1].is_covered = True
            case 'block':
                RULES['stmt'].expansions[2].is_covered = True
            case 'if':
                RULES['stmt'].expansions[3].is_covered = True
                for token in get_all_tokens(tree):
                    if token == 'else':
                        RULES['stmt'].expansions[3].is_optional_covered = True
                        break
            case 'while':
                RULES['stmt'].expansions[4].is_covered = True
            case 'return':
                RULES['stmt'].expansions[5].is_covered = True
            case _:
                raise Exception(f"Unknown stmt type {rules}")

    def exp(self, tree: Tree):
        RULES['exp'].expansions[0].is_covered = True

    def cond(self, tree: Tree):
        RULES['cond'].expansions[0].is_covered = True

    def l_val(self, tree: Tree):
        RULES['l_val'].expansions[0].is_covered = True
        tokens = get_all_tokens(tree)
        if tokens.count('[') >= 1:
            RULES['l_val'].expansions[0].is_repeat_covered = True

    def primary_exp(self, tree: Tree):
        if isinstance(tree.children[0], Token):
            type = tree.children[0].value
        else:
            type = tree.children[0].data.value
        match type:
            case '(':
                RULES['primary_exp'].expansions[0].is_covered = True
            case 'l_val':
                RULES['primary_exp'].expansions[1].is_covered = True
            case 'number':
                RULES['primary_exp'].expansions[2].is_covered = True
            case _:
                raise Exception(f"Unknown primary_exp type {type}")

    def number(self, tree: Tree):
        RULES['number'].expansions[0].is_covered = True

    def unary_exp(self, tree: Tree):
        if isinstance(tree.children[0], Tree):
            type = tree.children[0].data.value
        else:
            type = tree.children[0].value
        match type:
            case 'primary_exp':
                RULES['unary_exp'].expansions[0].is_covered = True
            case 'unary_op':
                RULES['unary_exp'].expansions[2].is_covered = True
            case _:
                RULES['unary_exp'].expansions[1].is_covered = True
                rules = get_all_rules(tree)
                if rules.count('func_r_params') == 0:
                    RULES['unary_exp'].expansions[1].is_optional_covered = True

    def unary_op(self, tree: Tree):
        op = tree.children[0].value
        match op:
            case '+':
                RULES['unary_op'].expansions[0].is_covered = True
            case '-':
                RULES['unary_op'].expansions[1].is_covered = True
            case '!':
                RULES['unary_op'].expansions[2].is_covered = True
            case _:
                raise Exception(f"Unknown unary_op {op}")

    def func_r_params(self, tree: Tree):
        RULES['func_r_params'].expansions[0].is_covered = True
        rules = get_all_rules(tree)
        if rules.count('exp') > 1:
            RULES['func_r_params'].expansions[0].is_repeat_covered = True

    def mul_exp(self, tree: Tree):
        type = tree.children[0].data.value
        match type:
            case 'unary_exp':
                RULES['mul_exp'].expansions[0].is_covered = True
            case 'mul_exp':
                RULES['mul_exp'].expansions[1].is_covered = True
            case _:
                raise Exception(f"Unknown mul_exp type {type}")

    def mul_op(self, tree: Tree):
        op = tree.children[0].value
        match op:
            case '*':
                RULES['mul_op'].expansions[0].is_covered = True
            case '/':
                RULES['mul_op'].expansions[1].is_covered = True
            case '%':
                RULES['mul_op'].expansions[2].is_covered = True
            case _:
                raise Exception(f"Unknown mul_op {op}")

    def add_exp(self, tree: Tree):
        type = tree.children[0].data.value
        match type:
            case 'mul_exp':
                RULES['add_exp'].expansions[0].is_covered = True
            case 'add_exp':
                RULES['add_exp'].expansions[1].is_covered = True
            case _:
                raise Exception(f"Unknown add_exp type {type}")

    def add_op(self, tree: Tree):
        op = tree.children[0].value
        match op:
            case '+':
                RULES['add_op'].expansions[0].is_covered = True
            case '-':
                RULES['add_op'].expansions[1].is_covered = True
            case _:
                raise Exception(f"Unknown add_op {op}")

    def rel_exp(self, tree: Tree):
        type = tree.children[0].data.value
        match type:
            case 'add_exp':
                RULES['rel_exp'].expansions[0].is_covered = True
            case 'rel_exp':
                RULES['rel_exp'].expansions[1].is_covered = True
            case _:
                raise Exception(f"Unknown rel_exp type {type}")

    def rel_op(self, tree: Tree):
        op = tree.children[0].value
        match op:
            case '<':
                RULES['rel_op'].expansions[0].is_covered = True
            case '<=':
                RULES['rel_op'].expansions[1].is_covered = True
            case '>':
                RULES['rel_op'].expansions[2].is_covered = True
            case '>=':
                RULES['rel_op'].expansions[3].is_covered = True
            case _:
                raise Exception(f"Unknown rel_op {op}")

    def eq_exp(self, tree: Tree):
        type = tree.children[0].data.value
        match type:
            case 'rel_exp':
                RULES['eq_exp'].expansions[0].is_covered = True
            case 'eq_exp':
                RULES['eq_exp'].expansions[1].is_covered = True
            case _:
                raise Exception(f"Unknown eq_exp type {type}")

    def eq_op(self, tree: Tree):
        op = tree.children[0].value
        match op:
            case '==':
                RULES['eq_op'].expansions[0].is_covered = True
            case '!=':
                RULES['eq_op'].expansions[1].is_covered = True
            case _:
                raise Exception(f"Unknown eq_op {op}")

    def l_and_exp(self, tree: Tree):
        type = tree.children[0].data.value
        match type:
            case 'eq_exp':
                RULES['l_and_exp'].expansions[0].is_covered = True
            case 'l_and_exp':
                RULES['l_and_exp'].expansions[1].is_covered = True
            case _:
                raise Exception(f"Unknown l_and_exp type {type}")

    def l_or_exp(self, tree: Tree):
        type = tree.children[0].data.value
        match type:
            case 'l_and_exp':
                RULES['l_or_exp'].expansions[0].is_covered = True
            case 'l_or_exp':
                RULES['l_or_exp'].expansions[1].is_covered = True
            case _:
                raise Exception(f"Unknown l_or_exp type {type}")


def coverage(text, verbose=False):
    try:
        text_tree = text_parser.parse(text)
    except UnexpectedInput as e:
        print(red('Parse Error'))
        print(e)
        exit(1)
    if verbose:
        print(green("Parse Success"))
        print(text_tree.pretty())
    CoverageVisitor().visit_topdown(text_tree)


def report(verbose):
    uncovered = []
    for rule in RULES.values():
        if not rule.full_coverage():
            uncovered.append(rule)
    if len(uncovered) == 0:
        print(green("All rules are covered!"))
        exit(0)
    else:
        print(red("Some rules are not covered:"))
        for rule in uncovered:
            if verbose:
                print(repr(rule))
            else:
                print(rule)
        exit(1)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-v', '--verbose', action='store_true', default=False, help='Print verbose output')
    arg_parser.add_argument('files',  nargs='+', help='Files to check')
    args = arg_parser.parse_args()
    for file in args.files:
        with open(file, 'r') as f:
            text = f.read()
        coverage(text, verbose=args.verbose)
    report(verbose=args.verbose)
