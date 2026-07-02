#include "type_checker.hpp"

#include "common.hpp"

TypeChecker::TypeChecker() {
  // 你需要在这里对 symbol_table 进行初始化
  // 插入一些内置函数，如 read 和 write
  symbol_table.add_symbol("read", FuncType::create(PrimitiveType::Int, {}));
  symbol_table.add_symbol("write", FuncType::create(PrimitiveType::Void, {PrimitiveType::Int}));
}

TypePtr TypeChecker::check(AST::NodePtr node) {
#define CHECK_NODE(type)                                     \
  if (auto n = std::dynamic_pointer_cast<AST::type>(node)) { \
    return check##type(n);                                   \
  }

  // 递归检查 AST 的每个节点
  // 如果你添加了新的 AST 节点类型，记得在这里添加对应的检查函数
  CHECK_NODE(CompUnit)
  CHECK_NODE(FuncDef)
  CHECK_NODE(VarDecl)
  CHECK_NODE(Block)
  CHECK_NODE(AssignStmt)
  CHECK_NODE(ReturnStmt)
  CHECK_NODE(LVal)
  CHECK_NODE(IntConst)
  CHECK_NODE(FuncCall)
  CHECK_NODE(UnaryExp)
  CHECK_NODE(BinaryExp)
  CHECK_NODE(IfStmt)
  CHECK_NODE(WhileStmt)
  CHECK_NODE(ExpStmt)
  CHECK_NODE(EmptyStmt)

// #warning Add more AST node types if needed

#undef CHECK_NODE

  ASSERT(false, "Unknown AST node type " + node->to_string() +
                    " in type checking at line " +
                    std::to_string(node->lineno));
}

TypePtr TypeChecker::checkCompUnit(AST::CompUnitPtr node) {
  for (auto& unit : node->units) {
    check(unit);
  }
  return nullptr;
}

TypePtr convert_to_typeptr(BasicType basic_type) {
  if (basic_type == BasicType::Int) {
    return PrimitiveType::Int;
  } else if (basic_type == BasicType::Void) {
    return PrimitiveType::Void;
  } else {
    return nullptr;
  }
}

TypePtr TypeChecker::convertFuncParamType(AST::FuncFParamPtr node) {
  if (!node->is_array_flag) {
    return convert_to_typeptr(node->btype);
  }

  std::vector<int> dims;
  dims.push_back(0);
  for (int dim : node->dims) {
    dims.push_back(dim);
  }
  return ArrayType::create(node->btype, dims);
}

bool TypeChecker::compatibleFuncArg(TypePtr param_type, TypePtr arg_type) {
  auto param_array = std::dynamic_pointer_cast<ArrayType>(param_type);
  auto arg_array = std::dynamic_pointer_cast<ArrayType>(arg_type);
  if (!param_array || param_array->dims.empty() || param_array->dims[0] != 0) {
    return param_type && arg_type && param_type->compatible(arg_type);
  }

  if (!arg_array || param_array->basic_type != arg_array->basic_type ||
      param_array->dims.size() != arg_array->dims.size()) {
    return false;
  }

  for (int i = 1; i < param_array->dims.size(); ++i) {
    if (param_array->dims[i] != arg_array->dims[i]) {
      return false;
    }
  }
  return true;
}

void TypeChecker::checkScalarInitializer(AST::InitValPtr init,
                                         TypePtr target_type) {
  if (!init->elements.empty() || !init->exp) {
    throw CompileError(ErrorCode::ExcessInitializers,
                       "excess elements in scalar initializer");
  }

  auto init_type = check(init->exp);
  if (!target_type->compatible(init_type)) {
    throw CompileError(ErrorCode::IncompatibleConversion,
                       "incompatible conversion/assignment");
  }
}

void TypeChecker::checkArrayInitializer(AST::InitValPtr init,
                                        BasicType basic_type,
                                        const std::vector<int>& dims) {
  if (init->exp) {
    throw CompileError(ErrorCode::InvalidInitializer,
                       "array initializer must be an initializer list");
  }

  std::vector<int> suffix_sizes(dims.size() + 1, 1);
  for (int i = static_cast<int>(dims.size()) - 1; i >= 0; --i) {
    suffix_sizes[i] = dims[i] * suffix_sizes[i + 1];
  }
  checkInitList(init, basic_type, suffix_sizes, 0, suffix_sizes[0]);
}

int TypeChecker::chooseSubarrayLevel(int filled, int current_level,
                                     const std::vector<int>& suffix_sizes) {
  int last_array_level = static_cast<int>(suffix_sizes.size()) - 2;
  for (int level = current_level + 1; level <= last_array_level; ++level) {
    if (filled % suffix_sizes[level] == 0) {
      return level;
    }
  }
  return -1;
}

int TypeChecker::checkInitList(AST::InitValPtr init, BasicType basic_type,
                               const std::vector<int>& suffix_sizes,
                               int current_level, int capacity) {
  int filled = 0;
  TypePtr scalar_type = convert_to_typeptr(basic_type);

  for (const auto& element : init->elements) {
    if (filled >= capacity) {
      throw CompileError(ErrorCode::ExcessInitializers,
                         "excess elements in array initializer");
    }

    if (element->exp) {
      auto element_type = check(element->exp);
      if (!scalar_type->compatible(element_type)) {
        throw CompileError(ErrorCode::IncompatibleConversion,
                           "incompatible conversion/assignment");
      }
      ++filled;
    } else {
      int sub_level = chooseSubarrayLevel(filled, current_level, suffix_sizes);
      if (sub_level < 0) {
        throw CompileError(ErrorCode::ExcessInitializers,
                           "excess elements in scalar initializer");
      }

      int sub_capacity = suffix_sizes[sub_level];
      if (filled + sub_capacity > capacity) {
        throw CompileError(ErrorCode::ExcessInitializers,
                           "excess elements in array initializer");
      }

      checkInitList(element, basic_type, suffix_sizes, sub_level, sub_capacity);
      filled += sub_capacity;
    }
  }

  return capacity;
}

TypePtr TypeChecker::checkFuncDef(AST::FuncDefPtr node) {
  // 在这个函数中，你需要判断函数是否已经被定义过
  // 如果函数已经被定义过，你需要报错
  // 否则，你需要将函数插入符号表，并在符号表中创建一个新的作用域
  // 再将函数参数也插入符号表，并将符号表中对应的 symbol 挂到 FuncDef 节点上
  // 最后检查函数体的语句块
  if (symbol_table.find_symbol(node->name)) {
    throw CompileError(ErrorCode::Redefinition, "redefinition of identifier");
  } else {
    TypePtr return_type = convert_to_typeptr(node->return_btype);
    std::vector<TypePtr> param_types;
    std::vector<AST::FuncFParamPtr> fps;
    if (node->fps && !node->fps->fps.empty()) {
      fps = node->fps->fps;
      for (const auto fp : fps) {
        param_types.push_back(convertFuncParamType(fp));
      }
    }
    node->symbol = symbol_table.add_symbol(node->name, FuncType::create(return_type, param_types));
    symbol_table.enter_scope();
      
    for (int i = 0; i < fps.size(); ++i) {
      fps[i]->symbol = symbol_table.add_symbol(fps[i]->name, param_types[i]);
      if (!fps[i]->symbol) {
        throw CompileError(ErrorCode::Redefinition, "redefinition of identifier");
      }
    }
    TypePtr old_return_type = current_return_type;
    current_return_type = return_type;
    checkBlock(node->block, false);
    current_return_type = old_return_type;
    symbol_table.exit_scope();
  }
  return nullptr;
}

TypePtr TypeChecker::checkVarDecl(AST::VarDeclPtr node) {
  for (auto var_def : node->defs) {
    checkVarDef(var_def, node->btype);
  }
  return nullptr;
}

TypePtr TypeChecker::checkVarDef(AST::VarDefPtr node, BasicType var_type) {  
  // 判断变量是否已经被定义过
  // 如果有初始化表达式，你需要检查初始化表达式的类型是否和变量类型相同
  // 如果是数组，你还需要检查初始化表达式和数组的维度是否匹配，是否有溢出的情况
  if (symbol_table.find_symbol(node->ident, true)) {
    throw CompileError(ErrorCode::Redefinition, "redefinition of identifier");
  }

  TypePtr type;
  if (node->dims.empty()) {
    type = PrimitiveType::create(var_type);
    if (node->ivp) {
      checkScalarInitializer(node->ivp, type);
    }
  } else {
    type = ArrayType::create(var_type, node->dims);
    if (node->ivp) {
      checkArrayInitializer(node->ivp, var_type, node->dims);
    }
  }

  // 将变量插入符号表，并将符号表中的 symbol 挂到 VarDef 节点上
  node->symbol = symbol_table.add_symbol(node->ident, type);
  if (!node->symbol) {
    throw CompileError(ErrorCode::Redefinition, "redefinition of identifier");
  }
  return nullptr;
}

TypePtr TypeChecker::checkBlock(AST::BlockPtr node, bool new_scope) {
  // 检查块内的每个语句
  // 如果 new_scope 为 true
  // 你需要在进入和退出块时更新符号表，创建、销毁新的作用域
  if (new_scope) {
    symbol_table.enter_scope();
  }

  const auto& stmts = node->stmts;
  for (const auto stmt : stmts) {
    check(stmt);
  }

  if (new_scope) {
    symbol_table.exit_scope();
  }

  return nullptr;
}

TypePtr TypeChecker::checkAssignStmt(AST::AssignStmtPtr node) {
  TypePtr lval_type = check(node->lval);
  TypePtr expr_type = check(node->exp);
  // 判断赋值号两边的类型是否相同
  // 我们实验中只支持 int 类型
  // 因此你需要判断 lval_type 和 expr_type 是否都为 int 类型
  if (std::dynamic_pointer_cast<ArrayType>(lval_type)) {
    throw CompileError(ErrorCode::NotAssignable,
                       "array type is not assignable");
  }
  if (!lval_type || !expr_type || !lval_type->compatible(expr_type)) {
    throw CompileError(ErrorCode::IncompatibleConversion,
                       "incompatible conversion/assignment");
  }

  return lval_type;
}

TypePtr TypeChecker::checkReturnStmt(AST::ReturnStmtPtr node) {
  // 判断返回值类型是否和函数声明的返回值类型相同
  if (!current_return_type) {
    throw CompileError(ErrorCode::ReturnMismatch, "return type mismatch");
  }
  if (!node->exp) {
    if (!current_return_type->compatible(PrimitiveType::Void)) {
      throw CompileError(ErrorCode::ReturnMismatch, "return type mismatch");
    }
    return nullptr;
  }

  auto return_type = check(node->exp);
  if (!return_type || !current_return_type->compatible(return_type)) {
    throw CompileError(ErrorCode::ReturnMismatch, "return type mismatch");
  }

  return nullptr;
}

TypePtr TypeChecker::checkLVal(AST::LValPtr node) {
  // 你需要在这里查找符号表，判断变量是否被定义过
  // 根据符号表中的信息设置 LVal 的类型
  // 若变量未定义，你需要报错
  // 否则，将符号表中的 symbol 挂到 LVal 节点上
  // 如果 LVal 是数组，你还需要根据下标索引来设置 LVal 的类型
  auto symbol = symbol_table.find_symbol(node->ident);
  if (!symbol) {
    throw CompileError(ErrorCode::Undeclared, "use of undeclared identifier");
  }
  node->symbol = symbol;
  if (node->dims.size()) {
    auto array_type = std::dynamic_pointer_cast<ArrayType>(symbol->type);
    if (!array_type || node->dims.size() > array_type->dims.size()) {
      throw CompileError(ErrorCode::NotSubscriptable,
                         "subscripted value is not an array or pointer");
    }
    for (const auto& dim : node->dims) {
      auto dim_type = check(dim);
      if (!dim_type || !dim_type->compatible(PrimitiveType::Int)) {
        throw CompileError(ErrorCode::NotIntegerSubscript,
                           "array subscript is not an integer");
      }
    }
    if (node->dims.size() == array_type->dims.size()) {
      return convert_to_typeptr(array_type->basic_type);
    }
    std::vector<int> remaining_dims(array_type->dims.begin() + node->dims.size(),
                                    array_type->dims.end());
    return ArrayType::create(array_type->basic_type, remaining_dims);
  }

  // 你需要返回 LVal 的类型
  return symbol->type;
}

TypePtr TypeChecker::checkIntConst(AST::IntConstPtr node) {
  // 整数常量的类型是 int
  return PrimitiveType::Int;
}

TypePtr TypeChecker::checkFuncCall(AST::FuncCallPtr node) {
  // 首先需要查找函数是否被定义过
  // 然后需要判断函数调用的参数个数和类型是否和声明一致
  // 最后设置函数调用表达式的类型为函数的返回值类型
  // 并将函数的 symbol 挂到 FuncCall 节点上
  auto func_symbol = symbol_table.find_symbol(node->name);
  if (!func_symbol) {
    throw CompileError(ErrorCode::Undeclared, "use of undeclared identifier");
  }
  
  FuncTypePtr func_type = std::dynamic_pointer_cast<FuncType>(func_symbol->type);
  if (!func_type) {
    throw CompileError(ErrorCode::NotCallable,
                       "called object is not a function or function pointer");
  }

  if (func_type->param_types.size() == node->args.size()) {
    for (int i = 0; i < node->args.size(); ++i) {
      if (!compatibleFuncArg(func_type->param_types[i], check(node->args[i]))) {
        throw CompileError(ErrorCode::IncompatibleConversion,
                           "incompatible conversion/assignment");
      }
    }
  } else {
    throw CompileError(ErrorCode::ArityMismatch,
                       "function arguments number not matched");
  }

  node->symbol = func_symbol;

  // 你需要返回函数调用表达式的类型
  return func_type->return_type;
}

TypePtr TypeChecker::checkUnaryExp(AST::UnaryExpPtr node) {
  auto type = check(node->exp);
  // 一元表达式只支持 int 类型，因此你需要判断 type 是否为 int
  if (!type || !type->compatible(PrimitiveType::Int)) {
    throw CompileError(ErrorCode::InvalidOperands,
                       "invalid operands to unary expression");
  }

  return PrimitiveType::Int;
}

TypePtr TypeChecker::checkBinaryExp(AST::BinaryExpPtr node) {
  TypePtr left_type = check(node->left);
  TypePtr right_type = check(node->right);
  // 二元表达式只支持 int 类型，因此你需要判断左右表达式的类型是否为 int
  if (!left_type || !right_type || !left_type->compatible(PrimitiveType::Int) || !right_type->compatible(PrimitiveType::Int)) {
    throw CompileError(ErrorCode::InvalidOperands,
                       "invalid operands to binary expression");
  }

  return PrimitiveType::Int;
}

TypePtr TypeChecker::checkIfStmt(AST::IfStmtPtr node) {
  auto cond_type = check(node->cond);
  if (!cond_type || !cond_type->compatible(PrimitiveType::Int)) {
    throw CompileError(ErrorCode::IncompatibleConversion,
                       "condition expression must be int");
  }
  if (node->if_block) {
    check(node->if_block);
  }
  if (node->else_block) {
    check(node->else_block);
  }
  return nullptr;
}

TypePtr TypeChecker::checkWhileStmt(AST::WhileStmtPtr node) {
  auto cond_type = check(node->cond);
  if (!cond_type || !cond_type->compatible(PrimitiveType::Int)) {
    throw CompileError(ErrorCode::IncompatibleConversion,
                       "condition expression must be int");
  }
  if (node->block) {
    check(node->block);
  }
  return nullptr;
}

TypePtr TypeChecker::checkExpStmt(AST::ExpStmtPtr node) {
  if (node->exp) {
    check(node->exp);
  }
  return nullptr;
}

TypePtr TypeChecker::checkEmptyStmt(std::shared_ptr<AST::EmptyStmt> node) {
  return nullptr;
}
