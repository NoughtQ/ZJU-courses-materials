#ifndef CODEGEN_REG_ALLOCATOR_HPP
#define CODEGEN_REG_ALLOCATOR_HPP

class ASMEmitter;

#include "analysis/control_flow.hpp"

class RegAllocator {
 public:
  void allocate(Module& mod);
  void allocate(FunctionPtr& func);

 private:
  bool need_stack_slot(const ASM::Reg& reg);
  int get_stack_offset(FunctionPtr& func, std::map<ASM::Reg, int>& offsets, const ASM::Reg& reg);
};

#endif  // CODEGEN_REG_ALLOCATOR_HPP