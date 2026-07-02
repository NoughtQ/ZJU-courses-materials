#ifndef IR_IR_TRANSLATOR_HPP
#define IR_IR_TRANSLATOR_HPP

#include <memory>
#include <vector>

#include "ast/tree.hpp"
#include "ir/ir.hpp"

class IRTranslator {
 public:
  IR::Code translate(AST::NodePtr node);
  IR::Code translateExp(AST::NodePtr node, const std::string& place = "");
  IR::Code translateCond(AST::NodePtr node, const std::string& label_true, const std::string& label_false);

 private:
  IR::Code translateCompUnit(AST::CompUnitPtr node);
  IR::Code translateFuncDef(AST::FuncDefPtr node);
  IR::Code translateBlock(AST::BlockPtr node);
  IR::Code translateVarDecl(AST::VarDeclPtr node);
  IR::Code translateVarDef(AST::VarDefPtr node);
  IR::Code translateAssignStmt(AST::AssignStmtPtr node);
  IR::Code translateReturnStmt(AST::ReturnStmtPtr node);
  IR::Code translateLVal(AST::LValPtr node, const std::string& place = "");
  IR::Code translateBinaryExp(AST::BinaryExpPtr node,
                              const std::string& place = "");
  IR::Code translateUnaryExp(AST::UnaryExpPtr node,
                             const std::string& place = "");
  IR::Code translateFuncCall(AST::FuncCallPtr node,
                             const std::string& place = "");
  IR::Code translateIntConst(AST::IntConstPtr node,
                             const std::string& place = "");

  IR::Code translateIfStmt(AST::IfStmtPtr node);
  IR::Code translateWhileStmt(AST::WhileStmtPtr node);
  IR::Code translateExpStmt(AST::ExpStmtPtr node);
  IR::Code translateEmptyStmt(AST::EmptyStmtPtr node);

  std::string new_temp();
  std::string new_label();
  int array_size_bytes(const std::vector<int>& dims);
  int array_suffix_elems(const std::vector<int>& dims, int start);
  std::vector<int> array_suffix_sizes(const std::vector<int>& dims);
  void flatten_init_val(AST::InitValPtr init, std::vector<AST::NodePtr>& result);
  void flatten_global_init(AST::InitValPtr init, std::vector<int>& result);
  int choose_subarray_level(int filled, int current_level,
                            const std::vector<int>& suffix_sizes);
  void fill_local_array_init(AST::InitValPtr init, int current_level, int start,
                             int capacity,
                             const std::vector<int>& suffix_sizes,
                             std::vector<AST::NodePtr>& result);
  void fill_global_array_init(AST::InitValPtr init, int current_level, int start,
                              int capacity,
                              const std::vector<int>& suffix_sizes,
                              std::vector<int>& result);
  IR::Code translateLValAddr(AST::LValPtr node, const std::string& addr);
  bool is_global(SymbolPtr symbol) const;
  bool is_array(SymbolPtr symbol) const;
  bool is_relop(BinaryOp op) const;
  IR::Code assign_bool_from_cond(AST::NodePtr node, const std::string& place);

  bool in_function = false;
};

#endif  // IR_IR_TRANSLATOR_HPP
