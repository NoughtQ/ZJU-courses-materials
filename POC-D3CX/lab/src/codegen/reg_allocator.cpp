#include "reg_allocator.hpp"

#include <limits>
#include <map>
#include <set>
#include <vector>

bool RegAllocator::need_stack_slot(const ASM::Reg& reg) {
  return !reg.is_phys();
}

static bool is_temp_reg(const ASM::Reg& reg) {
  return !reg.name.empty() && reg.name[0] == 'T';
}

int RegAllocator::get_stack_offset(FunctionPtr& func, std::map<ASM::Reg, int>& offsets,
                     const ASM::Reg& reg) {
  auto it = offsets.find(reg);
  if (it != offsets.end()) {
    return it->second;
  }
  int offset = func->alloc_temp(4);
  offsets[reg] = offset;
  return offset;
}

void RegAllocator::allocate(Module& mod) {
  for (auto& func : mod.functions) {
    allocate(func);
  }
}

void RegAllocator::allocate(FunctionPtr& func) {
  func->alloc_reg(8);   // allocate space for return address and previous fp
  ASM::RegMap reg_map;  // virtual register to physical register
  std::map<ASM::Reg, int> stack_offsets;
  std::map<ASM::Reg, int> remaining_uses;
  std::vector<ASM::Reg> temp_regs = {ASM::Reg::t1, ASM::Reg::t2, ASM::Reg::t3,
                                     ASM::Reg::t4, ASM::Reg::t5};

  for (const BasicBlockPtr& block : func->blocks) {
    for (const auto& inst : block->asm_code) {
      for (const auto& reg : inst->get_uses()) {
        if (need_stack_slot(reg)) {
          remaining_uses[reg]++;
        }
      }
    }
  }

  struct CachedReg {
    ASM::Reg phys;
    bool dirty;
    int last_used;
  };
  // 在这里实现寄存器分配算法，将结果保存在 reg_map 中
  // tips: 对于朴素的算法，可能用不到 reg_map
  for (const BasicBlockPtr& block : func->blocks) {
    ASM::Code allocated_code;
    std::map<ASM::Reg, CachedReg> cache;
    std::map<ASM::Reg, ASM::Reg> owner;
    int timestamp = 0;

    auto flush_reg = [&](const ASM::Reg& virt, bool force) {
      auto cached = cache.find(virt);
      if (cached == cache.end()) {
        return;
      }
      if (cached->second.dirty &&
          (force || !is_temp_reg(virt) || remaining_uses[virt] > 0)) {
        int offset = get_stack_offset(func, stack_offsets, virt);
        allocated_code.push_back(
            ASM::Store::create(ASM::Reg::sp, cached->second.phys, offset));
      }
      owner.erase(cached->second.phys);
      cache.erase(cached);
    };

    auto flush_all = [&](bool force) {
      std::vector<ASM::Reg> regs;
      for (const auto& [virt, _] : cache) {
        regs.push_back(virt);
      }
      for (const auto& reg : regs) {
        flush_reg(reg, force);
      }
    };

    auto choose_reg = [&](const std::set<ASM::Reg>& protected_regs) {
      for (const auto& reg : temp_regs) {
        if (owner.find(reg) == owner.end() &&
            protected_regs.find(reg) == protected_regs.end()) {
          return reg;
        }
      }

      ASM::Reg victim = temp_regs.front();
      int oldest = std::numeric_limits<int>::max();
      bool found = false;
      for (const auto& [virt, cached] : cache) {
        if (protected_regs.find(cached.phys) != protected_regs.end()) {
          continue;
        }
        if (!found || cached.last_used < oldest) {
          victim = cached.phys;
          oldest = cached.last_used;
          found = true;
        }
      }
      ASSERT(found, "not enough temporary registers for one instruction");
      flush_reg(owner.at(victim), false);
      return victim;
    };

    auto ensure_use = [&](const ASM::Reg& virt,
                          const std::set<ASM::Reg>& protected_regs) {
      auto cached = cache.find(virt);
      if (cached != cache.end()) {
        cached->second.last_used = ++timestamp;
        return cached->second.phys;
      }
      ASM::Reg phys = choose_reg(protected_regs);
      int offset = get_stack_offset(func, stack_offsets, virt);
      allocated_code.push_back(ASM::Load::create(phys, ASM::Reg::sp, offset));
      cache.insert_or_assign(virt, CachedReg{phys, false, ++timestamp});
      owner.insert_or_assign(phys, virt);
      return phys;
    };

    auto ensure_def = [&](const ASM::Reg& virt,
                          const std::set<ASM::Reg>& protected_regs) {
      auto cached = cache.find(virt);
      if (cached != cache.end()) {
        cached->second.dirty = true;
        cached->second.last_used = ++timestamp;
        return cached->second.phys;
      }
      ASM::Reg phys = choose_reg(protected_regs);
      if (remaining_uses[virt] > 0) {
        get_stack_offset(func, stack_offsets, virt);
      }
      cache.insert_or_assign(virt, CachedReg{phys, true, ++timestamp});
      owner.insert_or_assign(phys, virt);
      return phys;
    };

    for (const auto& inst : block->asm_code) {
      ASM::RegMap use_map;
      ASM::RegMap def_map;
      std::set<ASM::Reg> protected_regs;

      bool is_barrier = type_of<ASM::Call>(inst) || type_of<ASM::Jump>(inst) ||
                        type_of<ASM::Branch>(inst);
      if (type_of<ASM::Label>(inst)) {
        flush_all(true);
        allocated_code.push_back(inst);
        continue;
      }

      for (const auto& reg : inst->get_uses()) {
        if (!need_stack_slot(reg)) {
          continue;
        }
        ASM::Reg temp = ensure_use(reg, protected_regs);
        protected_regs.insert(temp);
        use_map.insert_or_assign(reg, temp);
      }

      for (const auto& reg : inst->get_uses()) {
        if (!need_stack_slot(reg)) {
          continue;
        }
        remaining_uses[reg]--;
        if (is_temp_reg(reg) && remaining_uses[reg] == 0) {
          auto cached = cache.find(reg);
          if (cached != cache.end()) {
            owner.erase(cached->second.phys);
            cache.erase(cached);
          }
        }
      }

      if (is_barrier) {
        flush_all(true);
      }

      for (const auto& reg : inst->get_defs()) {
        if (!need_stack_slot(reg)) {
          continue;
        }
        ASM::Reg temp = ensure_def(reg, protected_regs);
        protected_regs.insert(temp);
        def_map.insert_or_assign(reg, temp);
      }

      inst->replace_uses(use_map);
      inst->replace_defs(def_map);
      allocated_code.push_back(inst);

      for (const auto& reg : inst->get_defs()) {
        if (!need_stack_slot(reg) || !is_temp_reg(reg) ||
            remaining_uses[reg] > 0) {
          continue;
        }
        auto cached = cache.find(reg);
        if (cached != cache.end()) {
          owner.erase(cached->second.phys);
          cache.erase(cached);
        }
      }

      if (is_barrier) {
        cache.clear();
        owner.clear();
      }
    }
    flush_all(true);
    block->asm_code = allocated_code;
  }

  func->reg_map = reg_map;
}
