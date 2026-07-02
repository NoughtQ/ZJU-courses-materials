#ifndef CODEGEN_INST_SELECTOR_HPP
#define CODEGEN_INST_SELECTOR_HPP

class ASMEmitter;

#include "analysis/control_flow.hpp"
#include "asm.hpp"
#include "ir/ir.hpp"

class InstSelector {
 public:
  void select(Module& mod);

 private:
  std::string func_name;
  FunctionPtr current_func;
  int param_count = 0;
  void select(FunctionPtr& func);
  ASM::Code select(const IR::Code& ir_code);
  ASM::Code select(const IR::NodePtr& node);
  ASM::Code selectLoadImm(const IR::LoadImmPtr& node);
  ASM::Code selectAssign(const IR::AssignPtr& node);
  ASM::Code selectBinary(const IR::BinaryPtr& node);
  ASM::Code selectUnary(const IR::UnaryPtr& node);
  ASM::Code selectLabel(const IR::LabelPtr& node);
  ASM::Code selectGoto(const IR::GotoPtr& node);
  ASM::Code selectFunction(const IR::FunctionPtr& node);
  ASM::Code selectCall(const IR::CallPtr& node);
  ASM::Code selectArg(const IR::ArgPtr& node);
  ASM::Code selectReturn(const IR::ReturnPtr& node);
  // newly added
  ASM::Code selectIf(const IR::IfPtr& node);
  ASM::Code selectParam(const IR::ParamPtr& node);
  ASM::Code selectDec(const IR::DecPtr& node);
  ASM::Code selectLoadLabel(const IR::LoadLabelPtr& node);
  ASM::Code selectLoad(const IR::LoadPtr& node);
  ASM::Code selectLoadElem(const IR::LoadElemPtr& node);
  ASM::Code selectStore(const IR::StorePtr& node);
  ASM::Code selectStoreElem(const IR::StoreElemPtr& node);
};

#endif  // CODEGEN_INST_SELECTOR_HPP
