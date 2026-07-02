#ifndef AST_TREE_HPP
#define AST_TREE_HPP

#include <iostream>
#include <memory>
#include <string>
#include <vector>

#include "common.hpp"
#include "semantic/symbol_table.hpp"

extern int yylineno;

namespace AST {

class Node;
using NodePtr = std::shared_ptr<Node>;
class Node {
public:
  int lineno;

  virtual std::vector<NodePtr> get_children() { return std::vector<NodePtr>(); }
  void print_tree(std::string prefix = "", std::string info_prefix = "");
  virtual std::string to_string() = 0;

  Node() : lineno(yylineno) {}
  virtual ~Node() = default;
};

class EmptyStmt;
using EmptyStmtPtr = std::shared_ptr<EmptyStmt>;
class EmptyStmt : public Node {
public:
  EmptyStmt() {}
  std::string to_string() override { return "EmptyStmt"; }
};


class IntConst;
using IntConstPtr = std::shared_ptr<IntConst>;
class IntConst : public Node {
public:
  int value;
  IntConst(int value) : value(value) {}
  std::string to_string() override {
    return "IntConst <value: " + std::to_string(value) + ">";
  }
};

class LVal;
using LValPtr = std::shared_ptr<LVal>;
class LVal : public Node {
public:
  std::string ident;
  std::vector<NodePtr> dims;
// #warning Have not support array yet
  SymbolPtr symbol;
  LVal(std::string ident) : ident(ident) {}
  LVal(std::string ident, NodePtr dim) : ident(ident) {
    add_dim(dim);
  }
  void add_dim(NodePtr dim) { dims.push_back(dim); }

  std::string to_string() override {
    std::string s = std::string("LVal <ident: ") + ident;
    if (!dims.empty()) {
      s += ", dims: " + std::to_string(dims.size());
    }
    return s + ">";
  }
};

class UnaryExp;
using UnaryExpPtr = std::shared_ptr<UnaryExp>;
class UnaryExp : public Node {
public:
  UnaryOp op;
  NodePtr exp;
  UnaryExp(UnaryOp op, NodePtr exp) : op(op), exp(exp) {}
  std::string to_string() override {
    return "UnaryExp <op: " + std::string(op_to_string(op)) + ">";
  }
  std::vector<NodePtr> get_children() override { return {exp}; }
};

class BinaryExp;
using BinaryExpPtr = std::shared_ptr<BinaryExp>;
class BinaryExp : public Node {
public:
  BinaryOp op;
  NodePtr left, right;

  BinaryExp(BinaryOp op, NodePtr left, NodePtr right)
      : op(op), left(left), right(right) {}
  std::string to_string() override {
    return "BinaryExp <op: " + std::string(op_to_string(op)) + ">";
  }
  std::vector<NodePtr> get_children() override { return {left, right}; }
};

class FuncCall;
using FuncCallPtr = std::shared_ptr<FuncCall>;
class FuncCall : public Node {
public:
  std::string name;
  std::vector<NodePtr> args;
  SymbolPtr symbol;
  FuncCall(std::string name) : name(std::move(name)) {}
  FuncCall(NodePtr exp) { add_arg(exp); }
  void add_arg(NodePtr exp) { args.push_back(exp); }
  std::string to_string() override { return std::string("FuncCall <name: ") + name + ">"; }
  std::vector<NodePtr> get_children() override { return args; }
};

class Block;
using BlockPtr = std::shared_ptr<Block>;
class Block : public Node {
public:
  std::vector<NodePtr> stmts;
  Block() {}
  Block(NodePtr stmt) { add_stmt(stmt); }
  void add_stmt(NodePtr stmt) { stmts.push_back(stmt); }
  std::string to_string() override { return "Block"; }
  std::vector<NodePtr> get_children() override { return stmts; }
};

class AssignStmt;
using AssignStmtPtr = std::shared_ptr<AssignStmt>;
class AssignStmt : public Node {
public:
  LValPtr lval;
  NodePtr exp;
  AssignStmt(LValPtr lval, NodePtr exp) : lval(lval), exp(exp) {}
  std::string to_string() override { return "AssignStmt"; }
  std::vector<NodePtr> get_children() override { return {lval, exp}; }
};

class ReturnStmt;
using ReturnStmtPtr = std::shared_ptr<ReturnStmt>;
class ReturnStmt : public Node {
public:
  NodePtr exp;
  ReturnStmt() : exp(nullptr) {}
  ReturnStmt(NodePtr exp) : exp(exp) {}
  std::string to_string() override { return "ReturnStmt"; }
  std::vector<NodePtr> get_children() override {
    return exp ? std::vector<NodePtr>{exp} : std::vector<NodePtr>();
  }
};

class InitVal;
using InitValPtr = std::shared_ptr<InitVal>;
class InitVal : public Node {
public:
  NodePtr exp;
  std::vector<InitValPtr> elements;

  InitVal(): exp(nullptr) {}
  InitVal(NodePtr exp): exp(exp) {}
  InitVal(InitValPtr init_val) {
    add_init_val(init_val);
  }
  void add_init_val(InitValPtr init_val) {
    elements.push_back(init_val);
  }
  std::string to_string() override {
    return "InitVal <kind: ";
  }
  std::vector<NodePtr> get_children() override { 
    std::vector<NodePtr> children(elements.size());
    for (int i = 0; i < elements.size(); ++i) {
      children[i] = elements[i];
    }
    return children;
  }
};

class VarDef;
using VarDefPtr = std::shared_ptr<VarDef>;
class VarDef : public Node {
public:
  std::string ident;
  SymbolPtr symbol;
  std::vector<int> dims;
  InitValPtr ivp = nullptr;

  VarDef(std::string ident) : ident(std::move(ident)) {}
  VarDef(std::string ident, int dim) : ident(std::move(ident)) {
    add_dim(dim);
  }
  void add_dim(int dim) { dims.emplace_back(dim); }
  void set_init(InitValPtr ivp) { this->ivp = ivp; }
  std::string to_string() override {
    std::string s = std::string("VarDef <ident: ") + ident;
    if (!dims.empty()) {
      s += ", dims: " + std::to_string(dims.size());
    }
    return s + ">";
  }
};

class VarDecl;
using VarDeclPtr = std::shared_ptr<VarDecl>;
class VarDecl : public Node {
public:
  BasicType btype;
  std::vector<VarDefPtr> defs;
  VarDecl(VarDefPtr def) : btype(BasicType::Unknown) { add_def(def); }
  void add_def(VarDefPtr def) { defs.push_back(def); }
  std::string to_string() override {
    return "VarDecl <btype: " + std::string(type_to_string(btype)) + ">";
  }
  std::vector<NodePtr> get_children() override {
    std::vector<NodePtr> children(defs.size());
    for (int i = 0; i < defs.size(); ++i) {
      children[i] = defs[i];
    }
    return children;
  }
};

class FuncFParam;
using FuncFParamPtr = std::shared_ptr<FuncFParam>;
class FuncFParam : public Node {
public:
  BasicType btype;
  std::string name;
  std::vector<int> dims;
  bool is_array_flag = false;
  SymbolPtr symbol;

  FuncFParam(std::string name) 
    : btype(BasicType::Unknown), name(name)
    {}
  FuncFParam(std::string name, int dim) 
    : btype(BasicType::Unknown), name(name) {
      add_dim(dim);
    }
  void add_dim(int dim) { dims.emplace_back(dim); }
  void set_array_flag() { is_array_flag = true; }
  std::string to_string() override {
    return "FuncFParam <btype: " + std::string(type_to_string(btype))
      + ", name: " + name + ">";
  }
};

class FuncFParams;
using FuncFParamsPtr = std::shared_ptr<FuncFParams>;
class FuncFParams : public Node {
public:
  std::vector<FuncFParamPtr> fps;

  FuncFParams(FuncFParamPtr fp) {
    add_func_param(fp);
  }
  void add_func_param(FuncFParamPtr fp) { fps.push_back(fp); }
  std::string to_string() override {
    return "FuncFParams";
  }
  std::vector<NodePtr> get_children() override { 
    std::vector<NodePtr> children(fps.size());
    for (int i = 0; i < fps.size(); ++i) {
      children[i] = fps[i];
    }
    return children;
  }
};

class FuncDef;
using FuncDefPtr = std::shared_ptr<FuncDef>;
class FuncDef : public Node {
public:
  enum Kind { HAS_PARAM, NO_PARAM };
  Kind kind;
  BasicType return_btype;
  std::string name;
  FuncFParamsPtr fps;
  BlockPtr block;
  SymbolPtr symbol;
  
  FuncDef(BasicType return_btype, std::string name, BlockPtr block)
      : kind(NO_PARAM), return_btype(return_btype), 
        name(std::move(name)), block(block)
      {}
  FuncDef(BasicType return_btype, std::string name, FuncFParamsPtr fps, BlockPtr block)
      : kind(HAS_PARAM), return_btype(return_btype), 
        name(std::move(name)), fps(fps), block(block)
      {}
  std::string to_string() override {
    return "FuncDef <return_btype: " +
           std::string(type_to_string(return_btype)) + ", name: " 
            + name + ", kind: " 
            + std::string(kind == NO_PARAM ? "NO_PARAM" : "HAS_PARAM") 
            + ">";
  }
  std::vector<NodePtr> get_children() override { return {block}; }
};

class CompUnit;
using CompUnitPtr = std::shared_ptr<CompUnit>;
class CompUnit : public Node {
public:
  std::vector<NodePtr> units;  // FuncDef or VarDecl
  CompUnit(NodePtr unit) { add_unit(unit); }
  void add_unit(NodePtr unit) { units.push_back(unit); }
  std::string to_string() override { return "CompUnit"; }
  std::vector<NodePtr> get_children() override { return units; }
};

// #warning More AST nodes are needed
class IfStmt;
using IfStmtPtr = std::shared_ptr<IfStmt>;
class IfStmt : public Node {
public:
  NodePtr cond, if_block, else_block = nullptr;

  IfStmt(NodePtr cond, NodePtr if_block)
    : cond(cond), if_block(if_block)
    {}
  IfStmt(NodePtr cond, NodePtr if_block, NodePtr else_block)
    : cond(cond), if_block(if_block), else_block(else_block) 
    {}
  std::string to_string() override {
    return "IfStmt" + std::string(else_block ? " with else clause" : "");
  }
  std::vector<NodePtr> get_children() override { 
    if (else_block)
        return { cond, if_block, else_block }; 
    else
        return { cond, if_block };
  }
};

class WhileStmt;
using WhileStmtPtr = std::shared_ptr<WhileStmt>;
class WhileStmt : public Node {
public:
  NodePtr cond, block;

  WhileStmt(NodePtr cond, NodePtr block)
    : cond(cond), block(block)
    {}
  std::string to_string() override {
    return "WhileStmt";
  }
  std::vector<NodePtr> get_children() override { 
    return { block }; 
  }
};

class ExpStmt;
using ExpStmtPtr = std::shared_ptr<ExpStmt>;
class ExpStmt : public Node {
public:
  NodePtr exp;
  ExpStmt(NodePtr exp) : exp(exp) {}
  std::string to_string() override {
    return "ExpStmt";
  }
  std::vector<NodePtr> get_children() override { return {exp}; }
};

}  // namespace AST

#endif  // AST_TREE_HPP