#include "asm_emitter.hpp"

void ASMEmitter::emit(const Module& mod) {
  if (!mod.globals.empty()) {
    output << ".data\n";
    for (const auto& node : mod.globals) {
      auto global = std::dynamic_pointer_cast<IR::Global>(node);
      if (!global) {
        continue;
      }
      output << global->x << ":\n";
      int cnt = global->k / 4;
      for (int i = 0; i < cnt; ++i) {
        output << "    .word ";
        if (global->elems.empty() || i >= global->elems.size()) {
          output << "0\n";
        } else {
          output << global->elems[i] << "\n";
        }
      }
    }
  }

  output << ".text\n";

  // 添加 Venus 的 read 和 write 系统调用
  if (use_venus) {
    output << R"(
    .globl read
read:
    li a0, 6
    ecall
    ret

    .globl write
write:
    mv a1, a0
    li a0, 1
    ecall
    ret

)";
  }

  for (const auto& func : mod.functions) {
    emit(func);
  }
}

void ASMEmitter::emit(const FunctionPtr& func) {
  reg_map = func->reg_map;  // 设置当前函数的寄存器映射

  // 添加 prologue，处理 sp, ra, fp 等寄存器
  int size = func->reg_stack_size + func->temp_stack_size;
  if (size % 16) size += 16 - (size % 16);
  output << ".globl " << func->name << "\n" << func->name << ":\n";
  output << "    "
         << ASM::ArithImm::create(ASM::Reg::sp, ASM::Reg::sp, -size,
                                  ASM::ArithImm::Op::Add)
                ->to_string()
         << "\n";
  output << "    "
         << ASM::Store::create(ASM::Reg::sp, ASM::Reg::ra, size - 4)
                ->to_string()
         << "\n";
  output << "    "
         << ASM::Store::create(ASM::Reg::sp, ASM::Reg::fp, size - 8)
                ->to_string()
         << "\n";
  output << "    "
         << ASM::ArithImm::create(ASM::Reg::fp, ASM::Reg::sp, size,
                                  ASM::ArithImm::Op::Add)
                ->to_string()
         << "\n";

  // 为了方便 emit epilogue，这里忽略 exit block，也就是最后一个 block
  for (size_t i = 0; i < func->blocks.size() - 1; i++) {
    emit(func->blocks[i]);
  }

  // 添加 epilogue，处理 sp, ra, fp 等寄存器
  output << func->name << ".ret:\n";
  output << "    "
         << ASM::Load::create(ASM::Reg::ra, ASM::Reg::sp, size - 4)
                ->to_string()
         << "\n";
  output << "    "
         << ASM::Load::create(ASM::Reg::fp, ASM::Reg::sp, size - 8)
                ->to_string()
         << "\n";
  output << "    "
         << ASM::ArithImm::create(ASM::Reg::sp, ASM::Reg::sp, size,
                                  ASM::ArithImm::Op::Add)
                ->to_string()
         << "\n";
  output << "    ret\n";
}

void ASMEmitter::emit(const BasicBlockPtr& block) {
  for (const auto& inst : block->asm_code) {
    emit(inst);
  }
}

void ASMEmitter::emit(const ASM::InstPtr& inst) {
  inst->replace_all(reg_map);
  if (type_of<ASM::Label>(inst)) {
    output << inst->to_string() << std::endl;
  } else {
    output << "    " << inst->to_string() << std::endl;
  }
}
