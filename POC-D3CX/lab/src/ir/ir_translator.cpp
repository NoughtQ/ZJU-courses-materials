#include "ir_translator.hpp"

#include <cassert>

bool IRTranslator::is_global(SymbolPtr symbol) const {
  return symbol && symbol->scope == 0;
}

bool IRTranslator::is_array(SymbolPtr symbol) const {
  return symbol && std::dynamic_pointer_cast<ArrayType>(symbol->type) != nullptr;
}

bool IRTranslator::is_relop(BinaryOp op) const {
  return op == BinaryOp::Eq || op == BinaryOp::Ne || op == BinaryOp::Lt ||
         op == BinaryOp::Gt || op == BinaryOp::Le || op == BinaryOp::Ge;
}

int IRTranslator::array_size_bytes(const std::vector<int>& dims) {
  int bytes = 4;
  for (int dim : dims) {
    bytes *= dim;
  }
  return bytes;
}

int IRTranslator::array_suffix_elems(const std::vector<int>& dims, int start) {
  int elems = 1;
  for (int i = start; i < static_cast<int>(dims.size()); ++i) {
    if (dims[i] != 0) {
      elems *= dims[i];
    }
  }
  return elems;
}

std::vector<int> IRTranslator::array_suffix_sizes(const std::vector<int>& dims) {
  std::vector<int> suffix_sizes(dims.size() + 1, 1);
  for (int i = static_cast<int>(dims.size()) - 1; i >= 0; --i) {
    suffix_sizes[i] = dims[i] * suffix_sizes[i + 1];
  }
  return suffix_sizes;
}

int IRTranslator::choose_subarray_level(
    int filled, int current_level, const std::vector<int>& suffix_sizes) {
  int last_array_level = static_cast<int>(suffix_sizes.size()) - 2;
  for (int level = current_level + 1; level <= last_array_level; ++level) {
    if (filled % suffix_sizes[level] == 0) {
      return level;
    }
  }
  return -1;
}

void IRTranslator::flatten_init_val(
    AST::InitValPtr init, std::vector<AST::NodePtr>& result) {
  if (!init) {
    return;
  }
  if (init->exp) {
    result.push_back(init->exp);
    return;
  }
  for (const auto& elem : init->elements) {
    flatten_init_val(elem, result);
  }
}

void IRTranslator::fill_local_array_init(
    AST::InitValPtr init, int current_level, int start, int capacity,
    const std::vector<int>& suffix_sizes, std::vector<AST::NodePtr>& result) {
  if (!init || init->exp) {
    if (init && init->exp && start < static_cast<int>(result.size())) {
      result[start] = init->exp;
    }
    return;
  }

  int filled = 0;
  for (const auto& elem : init->elements) {
    if (elem->exp) {
      result[start + filled] = elem->exp;
      ++filled;
    } else {
      int sub_level =
          choose_subarray_level(start + filled, current_level, suffix_sizes);
      int sub_capacity = suffix_sizes[sub_level];
      fill_local_array_init(elem, sub_level, start + filled, sub_capacity,
                            suffix_sizes, result);
      filled += sub_capacity;
    }
    if (filled >= capacity) {
      break;
    }
  }
}

void IRTranslator::fill_global_array_init(
    AST::InitValPtr init, int current_level, int start, int capacity,
    const std::vector<int>& suffix_sizes, std::vector<int>& result) {
  if (!init || init->exp) {
    if (init && init->exp && start < static_cast<int>(result.size())) {
      auto int_const = std::dynamic_pointer_cast<AST::IntConst>(init->exp);
      ASSERT(int_const, "global initializer must be an integer constant");
      result[start] = int_const->value;
    }
    return;
  }

  int filled = 0;
  for (const auto& elem : init->elements) {
    if (elem->exp) {
      auto int_const = std::dynamic_pointer_cast<AST::IntConst>(elem->exp);
      ASSERT(int_const, "global initializer must be an integer constant");
      result[start + filled] = int_const->value;
      ++filled;
    } else {
      int sub_level =
          choose_subarray_level(start + filled, current_level, suffix_sizes);
      int sub_capacity = suffix_sizes[sub_level];
      fill_global_array_init(elem, sub_level, start + filled, sub_capacity,
                             suffix_sizes, result);
      filled += sub_capacity;
    }
    if (filled >= capacity) {
      break;
    }
  }
}

void IRTranslator::flatten_global_init(
    AST::InitValPtr init, std::vector<int>& result) {
  if (!init) {
    return;
  }
  if (init->exp) {
    auto int_const = std::dynamic_pointer_cast<AST::IntConst>(init->exp);
    result.push_back(int_const->value);
    return;
  }
  for (const auto& elem : init->elements) {
    flatten_global_init(elem, result);
  }
}

std::string IRTranslator::new_temp() {
  static int temp_count = 0;
  return "T" + std::to_string(temp_count++);
}

std::string IRTranslator::new_label() {
  static int label_count = 0;
  return "L" + std::to_string(label_count++);
}

IR::Code IRTranslator::translate(AST::NodePtr node) {
#define TRANSLATE_NODE(type)                                 \
  if (auto n = std::dynamic_pointer_cast<AST::type>(node)) { \
    return translate##type(n);                               \
  }
  // 递归翻译 AST 的每个节点
  // 如果你添加了新的 AST 节点类型，记得在这里添加对应的翻译函数

  TRANSLATE_NODE(CompUnit)
  TRANSLATE_NODE(FuncDef)
  TRANSLATE_NODE(Block)
  TRANSLATE_NODE(VarDecl)
  TRANSLATE_NODE(VarDef)
  TRANSLATE_NODE(AssignStmt)
  TRANSLATE_NODE(ReturnStmt)
  TRANSLATE_NODE(LVal)
  TRANSLATE_NODE(BinaryExp)
  TRANSLATE_NODE(UnaryExp)
  TRANSLATE_NODE(FuncCall)
  TRANSLATE_NODE(IntConst)
  TRANSLATE_NODE(IfStmt)
  TRANSLATE_NODE(WhileStmt)
  TRANSLATE_NODE(ExpStmt)
  TRANSLATE_NODE(EmptyStmt)

#undef TRANSLATE_NODE

  ASSERT(false,
         "Unknown AST node type " + node->to_string() + " in IR translation");
}

IR::Code IRTranslator::translateExp(AST::NodePtr node,
                                    const std::string& place) {
#define TRANSLATE_EXP_NODE(type)                             \
  if (auto n = std::dynamic_pointer_cast<AST::type>(node)) { \
    return translate##type(n, place);                        \
  }

  TRANSLATE_EXP_NODE(BinaryExp)
  TRANSLATE_EXP_NODE(UnaryExp)
  TRANSLATE_EXP_NODE(FuncCall)
  TRANSLATE_EXP_NODE(IntConst)
  TRANSLATE_EXP_NODE(LVal)

#undef TRANSLATE_EXP_NODE

  ASSERT(false, "No translateExp for node " + node->to_string());
}

IR::Code IRTranslator::translateCompUnit(AST::CompUnitPtr node) {
  IR::Code ir;
  for (auto& unit : node->units) {
    auto unit_ir = translate(unit);
    std::move(unit_ir.begin(), unit_ir.end(), std::back_inserter(ir));
  }
  return ir;
}

IR::Code IRTranslator::translateFuncDef(AST::FuncDefPtr node) {
  IR::Code ir;
  ir.push_back(IR::Function::create(node->name));
  in_function = true;
  if (node->fps) {
    for (const auto& param : node->fps->fps) {
      ir.push_back(IR::Param::create(param->symbol->unique_name, node->name));
    }
  }
  auto block_ir = translate(node->block);
  in_function = false;
  std::move(block_ir.begin(), block_ir.end(), std::back_inserter(ir));
  return ir;
}

IR::Code IRTranslator::translateBlock(AST::BlockPtr node) {
  IR::Code ir;
  for (auto& stmt : node->stmts) {
    auto stmt_ir = translate(stmt);
    std::move(stmt_ir.begin(), stmt_ir.end(), std::back_inserter(ir));
  }
  return ir;
}

IR::Code IRTranslator::translateVarDecl(AST::VarDeclPtr node) {
  IR::Code ir;
  for (auto& def : node->defs) {
    auto def_ir = translate(def);
    std::move(def_ir.begin(), def_ir.end(), std::back_inserter(ir));
  }
  return ir;
}

IR::Code IRTranslator::translateVarDef(AST::VarDefPtr node) {
  IR::Code ir;
  // 添加变量定义指令
  // 如果有初始化表达式，则需要翻译初始化表达式
  // 可以用语义分析阶段挂在 VarDef 上的 symbol 来获取变量的类型以及唯一名称
  std::string unique_name = node->symbol->unique_name;
  if (in_function) {  // Local
    if (node->dims.empty()) {
      if (node->ivp && node->ivp->exp) {
        auto init_ir = translateExp(node->ivp->exp, unique_name);
        std::move(init_ir.begin(), init_ir.end(), std::back_inserter(ir));
      }
    } else {
      int bytes = array_size_bytes(node->dims);
      ir.push_back(IR::Dec::create(unique_name, bytes));
      if (node->ivp) {
        std::vector<AST::NodePtr> result(bytes / 4);
        auto suffix_sizes = array_suffix_sizes(node->dims);
        fill_local_array_init(node->ivp, 0, 0, bytes / 4, suffix_sizes, result);
        for (int i = 0; i < result.size(); ++i) {
          auto tmp = new_temp();
          if (result[i]) {
            auto init_ir = translateExp(result[i], tmp);
            std::move(init_ir.begin(), init_ir.end(), std::back_inserter(ir));
          } else {
            ir.push_back(IR::LoadImm::create(tmp, 0));
          }
          ir.push_back(IR::StoreElem::create(unique_name, tmp, i * 4));
        }
      }
    }
  } else {  // Global
    int bytes = node->dims.empty() ? 4 : array_size_bytes(node->dims);
    if (node->dims.empty()) {
      if (node->ivp) {
        std::vector<int> values;
        flatten_global_init(node->ivp, values);
        values.resize(1, 0);
        ir.push_back(IR::Global::create(unique_name, bytes, values));
      } else {
        ir.push_back(IR::Global::create(unique_name, bytes));
      }
    } else {
      if (node->ivp) {
        std::vector<int> values(bytes / 4, 0);
        auto suffix_sizes = array_suffix_sizes(node->dims);
        fill_global_array_init(node->ivp, 0, 0, bytes / 4, suffix_sizes,
                               values);
        ir.push_back(IR::Global::create(unique_name, bytes, values));
      } else {
        ir.push_back(IR::Global::create(unique_name, bytes));
      }
    }
  }

  return ir;
}

IR::Code IRTranslator::translateAssignStmt(AST::AssignStmtPtr node) {
  IR::Code ir;
  auto lnode = node->lval;
  auto rnode = node->exp;

  auto r_name = new_temp();
  auto r_ir = translateExp(rnode, r_name);
  std::move(r_ir.begin(), r_ir.end(), std::back_inserter(ir));

  if (lnode->dims.empty() && !is_global(lnode->symbol) &&
      !is_array(lnode->symbol)) {
    ir.push_back(IR::Assign::create(lnode->symbol->unique_name, r_name));
  } else {
    auto addr = new_temp();
    auto addr_ir = translateLValAddr(lnode, addr);
    std::move(addr_ir.begin(), addr_ir.end(), std::back_inserter(ir));
    ir.push_back(IR::Store::create(addr, r_name));
  }

  return ir;
}

IR::Code IRTranslator::translateReturnStmt(AST::ReturnStmtPtr node) {
  IR::Code ir;

  // 翻译返回值
  // 如果有返回值，则：
  // place = new_temp();
  // auto exp_ir = translateExp(node->exp, place);
  // return exp_ir + [RETURN place];
  // 否则：
  // return [RETURN];
  if (node->exp) {
    auto place = new_temp();
    auto exp_ir = translateExp(node->exp, place);
    std::move(exp_ir.begin(), exp_ir.end(), std::back_inserter(ir));
    ir.push_back(IR::Return::create(place));
  } else {
    ir.push_back(IR::Return::create());
  }
  return ir;
}

IR::Code IRTranslator::translateLVal(AST::LValPtr node,
                                     const std::string& place) {
  IR::Code ir;

  // 如果 place 不为空，则将 LVal 的值赋给 place
  // 如果是数组，你需要特殊考虑

  if (!place.empty()) {
    if (node->dims.empty() && !is_global(node->symbol) &&
        !is_array(node->symbol)) {
      ir.push_back(IR::Assign::create(place, node->symbol->unique_name));
    } else {
      auto addr = new_temp();
      auto addr_ir = translateLValAddr(node, addr);
      std::move(addr_ir.begin(), addr_ir.end(), std::back_inserter(ir));

      auto array_type = std::dynamic_pointer_cast<ArrayType>(node->symbol->type);
      if (array_type && node->dims.size() < array_type->dims.size()) {
        ir.push_back(IR::Assign::create(place, addr));
      } else {
        ir.push_back(IR::Load::create(place, addr));
      }
    }
  }

  return ir;
}

IR::Code IRTranslator::translateLValAddr(AST::LValPtr node,
                                         const std::string& addr) {
  IR::Code ir;
  const auto name = node->symbol->unique_name;
  std::string base;

  if (is_global(node->symbol)) {
    base = new_temp();
    ir.push_back(IR::LoadLabel::create(base, name));
  } else {
    base = name;
  }

  if (node->dims.empty()) {
    if (base != addr) {
      ir.push_back(IR::Assign::create(addr, base));
    }
    return ir;
  }

  auto array_type = std::dynamic_pointer_cast<ArrayType>(node->symbol->type);
  ASSERT(array_type, "subscripted LVal must have array type");

  std::string offset;
  bool has_offset = false;
  for (int i = 0; i < static_cast<int>(node->dims.size()); ++i) {
    auto index = new_temp();
    auto index_ir = translateExp(node->dims[i], index);
    std::move(index_ir.begin(), index_ir.end(), std::back_inserter(ir));

    int byte_stride = array_suffix_elems(array_type->dims, i + 1) * 4;
    auto stride = new_temp();
    auto term = new_temp();
    ir.push_back(IR::LoadImm::create(stride, byte_stride));
    ir.push_back(IR::Binary::create(term, index, BinaryOp::Mul, stride));

    if (!has_offset) {
      offset = term;
      has_offset = true;
    } else {
      auto next_offset = new_temp();
      ir.push_back(IR::Binary::create(next_offset, offset, BinaryOp::Add, term));
      offset = next_offset;
    }
  }

  if (has_offset) {
    ir.push_back(IR::Binary::create(addr, base, BinaryOp::Add, offset));
  } else if (base != addr) {
    ir.push_back(IR::Assign::create(addr, base));
  }
  return ir;
}

IR::Code IRTranslator::translateBinaryExp(AST::BinaryExpPtr node,
                                          const std::string& place) {
  IR::Code ir;
  if (node->op == BinaryOp::And || node->op == BinaryOp::Or ||
      is_relop(node->op)) {
    if (!place.empty()) {
      return assign_bool_from_cond(node, place);
    }
    return ir;
  }

  auto left_place = new_temp();
  auto right_place = new_temp();

  // 翻译左右子表达式
  auto left_ir = translateExp(node->left, left_place);
  auto right_ir = translateExp(node->right, right_place);

  std::move(left_ir.begin(), left_ir.end(), std::back_inserter(ir));
  std::move(right_ir.begin(), right_ir.end(), std::back_inserter(ir));

  // 添加二元运算指令
  if (!place.empty()) {
    ir.push_back(IR::Binary::create(place, left_place, node->op, right_place));
  }
  return ir;
}

IR::Code IRTranslator::translateUnaryExp(AST::UnaryExpPtr node,
                                         const std::string& place) {
  IR::Code ir;

  // 翻译子表达式
  // 如果 place 不为空，则将 UnaryExp 的值赋给 place

  if (node->op == UnaryOp::Not) {
    if (!place.empty()) {
      return assign_bool_from_cond(node, place);
    }
    return ir;
  }

  auto tmp = new_temp();
  auto exp_ir = translateExp(node->exp, tmp);
  std::move(exp_ir.begin(), exp_ir.end(), std::back_inserter(ir));
  if (!place.empty()) {
    ir.push_back(IR::Unary::create(place, node->op, tmp));
  }

  return ir;
}

IR::Code IRTranslator::translateFuncCall(AST::FuncCallPtr node,
                                         const std::string& place) {
  IR::Code ir;
  std::vector<std::string> arg_places;

  // 首先翻译参数表达式，并存在临时变量中
  // 接下来，添加参数传递指令和函数调用指令
  // 如果 place 不为空，则将函数调用的返回值赋给 place

  int cnt = 0;
  for (const auto& arg : node->args) {
    auto arg_place = new_temp();
    auto arg_ir = translateExp(arg, arg_place);
    std::move(arg_ir.begin(), arg_ir.end(), std::back_inserter(ir));
    arg_places.push_back(arg_place);
  }
  for (const auto& arg_place : arg_places) {
    ir.push_back(IR::Arg::create(arg_place, node->name, cnt++));
  }
  
  if (place.empty()) {
    ir.push_back(IR::Call::create(node->name));
  } else {
    ir.push_back(IR::Call::create(place, node->name));
  }
  
  return ir;
}

IR::Code IRTranslator::translateIntConst(AST::IntConstPtr node,
                                         const std::string& place) {
  IR::Code ir;
  // 添加赋值常量指令
  if (!place.empty()) {
    ir.push_back(IR::LoadImm::create(place, node->value));
  }
  return ir;
}

IR::Code IRTranslator::translateIfStmt(AST::IfStmtPtr node) {
  IR::Code ir;
  auto true_label = new_label();
  auto false_label = new_label();
  auto end_label = new_label();

  auto cond_ir = translateCond(node->cond, true_label, false_label);
  std::move(cond_ir.begin(), cond_ir.end(), std::back_inserter(ir));

  ir.push_back(IR::Label::create(true_label));
  auto if_ir = translate(node->if_block);
  std::move(if_ir.begin(), if_ir.end(), std::back_inserter(ir));
  ir.push_back(IR::Goto::create(end_label));

  ir.push_back(IR::Label::create(false_label));
  if (node->else_block) {
    auto else_ir = translate(node->else_block);
    std::move(else_ir.begin(), else_ir.end(), std::back_inserter(ir));
  }

  ir.push_back(IR::Label::create(end_label));

  return ir;
}

IR::Code IRTranslator::translateWhileStmt(AST::WhileStmtPtr node) {
  IR::Code ir;
  auto cond_label = new_label();
  auto body_label = new_label();
  auto end_label = new_label();

  ir.push_back(IR::Label::create(cond_label));
  auto cond_ir = translateCond(node->cond, body_label, end_label);
  std::move(cond_ir.begin(), cond_ir.end(), std::back_inserter(ir));

  ir.push_back(IR::Label::create(body_label));
  auto body_ir = translate(node->block);
  std::move(body_ir.begin(), body_ir.end(), std::back_inserter(ir));
  ir.push_back(IR::Goto::create(cond_label));

  ir.push_back(IR::Label::create(end_label));

  return ir;
}

IR::Code IRTranslator::translateExpStmt(AST::ExpStmtPtr node) {
  IR::Code ir;

  auto exp_ir = translateExp(node->exp);
  std::move(exp_ir.begin(), exp_ir.end(), std::back_inserter(ir));

  return ir;
}

IR::Code IRTranslator::translateEmptyStmt(AST::EmptyStmtPtr node) {
  IR::Code ir;

  return ir;
}

IR::Code IRTranslator::translateCond(AST::NodePtr node,
                                     const std::string& label_true,
                                     const std::string& label_false) {
  IR::Code ir;

  if (auto unary = std::dynamic_pointer_cast<AST::UnaryExp>(node);
      unary && unary->op == UnaryOp::Not) {
    return translateCond(unary->exp, label_false, label_true);
  }

  if (auto binary = std::dynamic_pointer_cast<AST::BinaryExp>(node)) {
    if (binary->op == BinaryOp::And) {
      auto mid_label = new_label();
      auto left_ir = translateCond(binary->left, mid_label, label_false);
      std::move(left_ir.begin(), left_ir.end(), std::back_inserter(ir));
      ir.push_back(IR::Label::create(mid_label));
      auto right_ir = translateCond(binary->right, label_true, label_false);
      std::move(right_ir.begin(), right_ir.end(), std::back_inserter(ir));
      return ir;
    }
    if (binary->op == BinaryOp::Or) {
      auto mid_label = new_label();
      auto left_ir = translateCond(binary->left, label_true, mid_label);
      std::move(left_ir.begin(), left_ir.end(), std::back_inserter(ir));
      ir.push_back(IR::Label::create(mid_label));
      auto right_ir = translateCond(binary->right, label_true, label_false);
      std::move(right_ir.begin(), right_ir.end(), std::back_inserter(ir));
      return ir;
    }
    if (is_relop(binary->op)) {
      auto left = new_temp();
      auto right = new_temp();
      auto left_ir = translateExp(binary->left, left);
      auto right_ir = translateExp(binary->right, right);
      std::move(left_ir.begin(), left_ir.end(), std::back_inserter(ir));
      std::move(right_ir.begin(), right_ir.end(), std::back_inserter(ir));
      ir.push_back(IR::If::create(left, right, binary->op, label_true));
      ir.push_back(IR::Goto::create(label_false));
      return ir;
    }
  }

  auto value = new_temp();
  auto zero = new_temp();
  auto exp_ir = translateExp(node, value);
  std::move(exp_ir.begin(), exp_ir.end(), std::back_inserter(ir));
  ir.push_back(IR::LoadImm::create(zero, 0));
  ir.push_back(IR::If::create(value, zero, BinaryOp::Ne, label_true));
  ir.push_back(IR::Goto::create(label_false));
  return ir;
}

IR::Code IRTranslator::assign_bool_from_cond(AST::NodePtr node,
                                             const std::string& place) {
  IR::Code ir;
  auto true_label = new_label();
  auto false_label = new_label();
  auto end_label = new_label();

  auto cond_ir = translateCond(node, true_label, false_label);
  std::move(cond_ir.begin(), cond_ir.end(), std::back_inserter(ir));
  ir.push_back(IR::Label::create(true_label));
  ir.push_back(IR::LoadImm::create(place, 1));
  ir.push_back(IR::Goto::create(end_label));
  ir.push_back(IR::Label::create(false_label));
  ir.push_back(IR::LoadImm::create(place, 0));
  ir.push_back(IR::Label::create(end_label));
  return ir;
}
