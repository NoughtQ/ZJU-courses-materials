#include "cfg_builder.hpp"

#include <unordered_map>

Module CFGBuilder::build(IR::Code code) {
  Module mod;
  IR::Code current_func;

  // 按函数分割IR代码
  for (const auto& inst : code) {
    if (std::dynamic_pointer_cast<IR::Global>(inst)) {
      mod.globals.push_back(inst);
      continue;
    }
    if (auto func = std::dynamic_pointer_cast<IR::Function>(inst)) {
      if (!current_func.empty()) {
        mod.functions.push_back(build_single_func(current_func));
        current_func.clear();
      }
    }
    current_func.push_back(inst);
  }

  if (!current_func.empty()) {
    mod.functions.push_back(build_single_func(current_func));
  }

  return mod;
}

FunctionPtr CFGBuilder::build_single_func(IR::Code code) {
  std::vector<BasicBlockPtr> blocks;
  std::unordered_map<std::string, BasicBlockPtr> label_to_block;
  std::string func_name;
  bool ret_void = true;  // 函数返回值是否为 void

  // 统一为一个 ret block 处理返回
  // 这里没有完成基本块划分，而是把所有函数体内的代码放在一个基本块中
  // 如果你想要更细粒度的基本块，可以参考实验文档修改这里的逻辑

#warning Only one block is created for the whole function body now

  BasicBlockPtr current_block = BasicBlock::create("entry");
  for (const auto& inst : code) {
    if (auto func = std::dynamic_pointer_cast<IR::Function>(inst)) {
      func_name = func->name;
      current_block->label = func_name + ".entry";
      current_block->ir_code.push_back(inst);
    } else if (auto ret = std::dynamic_pointer_cast<IR::Return>(inst)) {
      if (ret->x.empty()) {
        current_block->ir_code.push_back(IR::Goto::create(func_name + ".ret"));
      } else {
        current_block->ir_code.push_back(IR::Assign::create("a0", ret->x));
        current_block->ir_code.push_back(IR::Goto::create(func_name + ".ret"));
        ret_void = false;
      }
    } else {
      current_block->ir_code.push_back(inst);
    }
  }
  blocks.push_back(current_block);
  label_to_block[current_block->label] = current_block;

  // 添加 exit block，统一处理函数退出
  auto exit_block = BasicBlock::create(func_name + ".ret");
  exit_block->ir_code.push_back(IR::Label::create(func_name + ".ret"));
  if (!ret_void) {
    exit_block->ir_code.push_back(IR::Return::create("a0"));
  } else {
    exit_block->ir_code.push_back(IR::Return::create());
  }
  blocks.push_back(exit_block);
  label_to_block[func_name + ".ret"] = exit_block;

  return Function::create(func_name, blocks);
}

std::string CFGBuilder::new_label() {
  static int label_count = 0;
  return "LN" + std::to_string(label_count++);
}
