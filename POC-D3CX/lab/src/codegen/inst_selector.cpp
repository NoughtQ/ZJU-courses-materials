#include "inst_selector.hpp"

#include <algorithm>
#include <cassert>
#include <memory>
#include <string>

#include "codegen/asm_emitter.hpp"

void InstSelector::select(Module& mod) {
  for (auto& func : mod.functions) {
    select(func);
  }
}

void InstSelector::select(FunctionPtr& func) {
  // 设置当前函数
  // 如果是 DEC，需要调用当前函数中的 alloc_temp，在栈上分配空间
  current_func = func;
  param_count = 0;

  int outgoing_arg_stack_size = 0;
  for (const auto& block : func->blocks) {
    for (const auto& node : block->ir_code) {
      if (auto arg = std::dynamic_pointer_cast<IR::Arg>(node)) {
        if (arg->k >= 8) {
          outgoing_arg_stack_size =
              std::max(outgoing_arg_stack_size, (arg->k - 7) * 4);
        }
      }
    }
  }
  current_func->temp_stack_size =
      std::max(current_func->temp_stack_size, outgoing_arg_stack_size);

  for (auto& block : func->blocks) {
    block->asm_code = select(block->ir_code);
  }
}

ASM::Code InstSelector::select(const IR::Code& ir_code) {
  ASM::Code asm_code;
  for (const auto& node : ir_code) {
    auto code = select(node);
    asm_code.insert(asm_code.end(), code.begin(), code.end());
  }
  return asm_code;
}

ASM::Code InstSelector::select(const IR::NodePtr& node) {
#define SELECT_NODE(type)                                   \
  if (auto p = std::dynamic_pointer_cast<IR::type>(node)) { \
    return select##type(p);                                 \
  }

  // 对于每种不同类型的 IR 节点，调用相应的 select 函数
  // 如果你添加了新的 IR 节点类型，记得在这里添加对应的 select 函数
  SELECT_NODE(LoadImm)
  SELECT_NODE(Assign)
  SELECT_NODE(Binary)
  SELECT_NODE(Unary)
  SELECT_NODE(Label)
  SELECT_NODE(Goto)
  SELECT_NODE(Function)
  SELECT_NODE(Call)
  SELECT_NODE(Arg)
  SELECT_NODE(Return)
  SELECT_NODE(If)
  SELECT_NODE(Param)
  SELECT_NODE(Dec)
  SELECT_NODE(LoadLabel)
  SELECT_NODE(Load)
  SELECT_NODE(LoadElem)
  SELECT_NODE(Store)
  SELECT_NODE(StoreElem)

  assert(false && "Unknown IR node type");
}

ASM::Code InstSelector::selectLoadImm(const IR::LoadImmPtr& node) {
  ASM::Code code;
  // a = #t	-> li reg(a), t
  code.push_back(ASM::Li::create(ASM::Reg(node->x), node->k));
  return code;
}

ASM::Code InstSelector::selectAssign(const IR::AssignPtr& node) {
  ASM::Code code;
  // a = b	-> mv reg(a), reg(b)
  code.push_back(ASM::Mv::create(ASM::Reg(node->x), ASM::Reg(node->y)));
  return code;
}

ASM::Code InstSelector::selectBinary(const IR::BinaryPtr& node) {
  ASM::Code code;
  // a = b + c	-> add reg(a), reg(b), reg(c)
  ASM::Arith::Op op;
  switch (node->op) {
    case BinaryOp::Add:
      op = ASM::Arith::Op::Add;
      break;
    case BinaryOp::Sub:
      op = ASM::Arith::Op::Sub;
      break;
    case BinaryOp::Mul:
      op = ASM::Arith::Op::Mul;
      break;
    case BinaryOp::Div:
      op = ASM::Arith::Op::Div;
      break;
    case BinaryOp::Mod:
      op = ASM::Arith::Op::Rem;
      break;
    default:
      assert(false && "Unsupported binary op in instruction selection");
  }
  code.push_back(ASM::Arith::create(ASM::Reg(node->x), ASM::Reg(node->y), ASM::Reg(node->z), op));
  return code;
}

ASM::Code InstSelector::selectUnary(const IR::UnaryPtr& node) {
  ASM::Code code;
  // a = -b	-> sub reg(a), zero, reg(b)
  ASM::Arith::Op op;
  switch (node->op) {
    case UnaryOp::Pos:
      code.push_back(ASM::Mv::create(ASM::Reg(node->x), ASM::Reg(node->y)));
      break;
    case UnaryOp::Neg:
      op = ASM::Arith::Op::Sub;
      code.push_back(ASM::Arith::create(ASM::Reg(node->x), ASM::Reg::zero, ASM::Reg(node->y), op));
      break;
    case UnaryOp::Not:
      assert(false && "logical not should be lowered by translateCond");
      break;
  }
  return code;
}

ASM::Code InstSelector::selectLabel(const IR::LabelPtr& node) {
  ASM::Code code;
  // LABEL label:	-> label:
  code.push_back(ASM::Label::create(node->label));
  return code;
}

ASM::Code InstSelector::selectGoto(const IR::GotoPtr& node) {
  ASM::Code code;
  // GOTO label	-> j label
  code.push_back(ASM::Jump::create(node->label));
  return code;
}

ASM::Code InstSelector::selectFunction(const IR::FunctionPtr& node) {
  ASM::Code code;
  // ASMEmitter emits function entry labels together with prologue.
  return code;
}

ASM::Code InstSelector::selectCall(const IR::CallPtr& node) {
  ASM::Code code;
  // CALL func	-> call func
  // x = CALL func	-> call func; mv reg(x), a0
  code.push_back(ASM::Call::create(node->func));
  if (!node->x.empty()) {
    code.push_back(ASM::Mv::create(ASM::Reg(node->x), ASM::Reg::a0));
  }
  return code;
}

ASM::Code InstSelector::selectArg(const IR::ArgPtr& node) {
  ASM::Code code;
  // ARG x	-> mv ak, reg(x)
  // k is the index of the argument
  if (node->k < 8) {
    code.push_back(ASM::Mv::create(ASM::Reg("a" + std::to_string(node->k)), ASM::Reg(node->x)));
  } else {
    int offset = (node->k - 8) * 4;
    code.push_back(ASM::Store::create(ASM::Reg::sp, ASM::Reg(node->x), offset));
  }
  return code;
}

ASM::Code InstSelector::selectReturn(const IR::ReturnPtr& node) {
  ASM::Code code;
  // 已经在 cfg builder 中统一为一个 exit call
  // 因此只有 exit block 里有 return 语句
  // 在 asm emitter 中对每个函数处理时
  // 会忽略 exit block 并添加 epilogue
  // 因此这里不需要处理
  return code;
}

// newly added
ASM::Code InstSelector::selectIf(const IR::IfPtr& node) {
  ASM::Code code;
  ASM::Branch::Op op;
  switch (node->op) {
    case BinaryOp::Eq:
      op = ASM::Branch::Op::Eq;
      break;
    case BinaryOp::Ne:
      op = ASM::Branch::Op::Ne;
      break;
    case BinaryOp::Lt: case BinaryOp::Gt:
      op = ASM::Branch::Op::Lt;
      break;
    case BinaryOp::Le: case BinaryOp::Ge:
      op = ASM::Branch::Op::Ge;
      break;
    default:
      assert(false && "Unsupported IF op in instruction selection");
  }

  if (node->op == BinaryOp::Gt || node->op == BinaryOp::Le) {
    code.push_back(ASM::Branch::create(ASM::Reg(node->y), ASM::Reg(node->x), node->l, op));
  } else {
    code.push_back(ASM::Branch::create(ASM::Reg(node->x), ASM::Reg(node->y), node->l, op));
  }

  return code;
}

ASM::Code InstSelector::selectParam(const IR::ParamPtr& node) {
  ASM::Code code;
  if (param_count < 8) {
    code.push_back(ASM::Mv::create(ASM::Reg(node->x),
                                   ASM::Reg("a" + std::to_string(param_count))));
  } else {
    code.push_back(ASM::Load::create(ASM::Reg(node->x), ASM::Reg::fp,
                                     (param_count - 8) * 4));
  }
  param_count++;
  return code;
}

ASM::Code InstSelector::selectDec(const IR::DecPtr& node) {
  ASM::Code code;
  int offset = current_func->alloc_temp(node->k);
  code.push_back(ASM::ArithImm::create(ASM::Reg(node->x), ASM::Reg::sp, offset,
                                       ASM::ArithImm::Op::Add));
  return code;
}

ASM::Code InstSelector::selectLoadLabel(const IR::LoadLabelPtr& node) {
  ASM::Code code;
  code.push_back(ASM::La::create(ASM::Reg(node->x), node->l));
  return code;
}

ASM::Code InstSelector::selectLoad(const IR::LoadPtr& node) {
  ASM::Code code;
  code.push_back(ASM::Load::create(ASM::Reg(node->x), ASM::Reg(node->y), 0));
  return code;
}

ASM::Code InstSelector::selectLoadElem(const IR::LoadElemPtr& node) {
  ASM::Code code;
  code.push_back(ASM::Load::create(ASM::Reg(node->x), ASM::Reg(node->y), node->k));
  return code;
}

ASM::Code InstSelector::selectStore(const IR::StorePtr& node) {
  ASM::Code code;
  code.push_back(ASM::Store::create(ASM::Reg(node->x), ASM::Reg(node->y), 0));
  return code;
}

ASM::Code InstSelector::selectStoreElem(const IR::StoreElemPtr& node) {
  ASM::Code code;
  code.push_back(ASM::Store::create(ASM::Reg(node->x), ASM::Reg(node->y), node->k));
  return code;
}
