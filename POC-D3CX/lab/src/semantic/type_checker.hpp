#ifndef SEMANTIC_TYPE_CHECKER_HPP
#define SEMANTIC_TYPE_CHECKER_HPP

#include <memory>

#include "ast/tree.hpp"
#include "symbol_table.hpp"

class TypeChecker {
 public:
  TypeChecker();

  TypePtr check(AST::NodePtr node);

 private:
  /// @brief The symbol table
  SymbolTable symbol_table;
  TypePtr current_return_type = nullptr;

  TypePtr checkIntConst(AST::IntConstPtr node);
  TypePtr checkLVal(AST::LValPtr node);
  TypePtr checkUnaryExp(AST::UnaryExpPtr node);
  TypePtr checkBinaryExp(AST::BinaryExpPtr node);
  TypePtr checkFuncCall(AST::FuncCallPtr node);
  TypePtr checkBlock(AST::BlockPtr node, bool new_scope = true);
  TypePtr checkAssignStmt(AST::AssignStmtPtr node);
  TypePtr checkReturnStmt(AST::ReturnStmtPtr node);
  TypePtr checkVarDef(AST::VarDefPtr node, BasicType var_type);
  TypePtr checkVarDecl(AST::VarDeclPtr node);
  TypePtr checkFuncDef(AST::FuncDefPtr node);
  TypePtr checkCompUnit(AST::CompUnitPtr node);
  TypePtr checkIfStmt(AST::IfStmtPtr node);
  TypePtr checkWhileStmt(AST::WhileStmtPtr node);
  TypePtr checkExpStmt(AST::ExpStmtPtr node);
  TypePtr checkEmptyStmt(std::shared_ptr<AST::EmptyStmt> node);

  TypePtr convertFuncParamType(AST::FuncFParamPtr node);
  bool compatibleFuncArg(TypePtr param_type, TypePtr arg_type);
  void checkScalarInitializer(AST::InitValPtr init, TypePtr target_type);
  void checkArrayInitializer(AST::InitValPtr init, BasicType basic_type,
                             const std::vector<int>& dims);
  int checkInitList(AST::InitValPtr init, BasicType basic_type,
                    const std::vector<int>& suffix_sizes, int current_level,
                    int capacity);
  int chooseSubarrayLevel(int filled, int current_level,
                          const std::vector<int>& suffix_sizes);
};

#endif  // SEMANTIC_TYPE_CHECKER_HPP
