#ifndef CODEGEN_ASM_EMITTER_HPP
#define CODEGEN_ASM_EMITTER_HPP

#include "analysis/control_flow.hpp"
#include "asm.hpp"
#include "inst_selector.hpp"
#include "reg_allocator.hpp"

class ASMEmitter {
 public:
  ASMEmitter(bool use_venus = false, std::ostream& output = std::cout)
      : use_venus(use_venus), output(output) {}
  void emit(const Module& mod);

 private:
  bool use_venus;
  std::ostream& output;
  ASM::RegMap reg_map;

  void emit(const FunctionPtr& func);
  void emit(const BasicBlockPtr& block);
  void emit(const ASM::InstPtr& inst);
};

#endif  // CODEGEN_ASM_EMITTER_HPP