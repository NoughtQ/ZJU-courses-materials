#include "type.hpp"

#include "common.hpp"

bool PrimitiveType::compatible(const TypePtr& other) const {
  auto other_type = std::dynamic_pointer_cast<PrimitiveType>(other);
  return other_type && basic_type == other_type->basic_type;
}

bool ArrayType::compatible(const TypePtr& other) const {
  auto other_type = std::dynamic_pointer_cast<ArrayType>(other);
  if (!other_type || basic_type != other_type->basic_type || dims.size() != other_type->dims.size()) {
    return false;
  }
  for (int i = 0; i < dims.size(); ++i) {
    if (dims[i] != other_type->dims[i]) {
      return false;
    }
  }
  return true;
}

bool FuncType::compatible(const TypePtr& other) const {
  auto other_type = std::dynamic_pointer_cast<FuncType>(other);
  if (!other_type || !return_type->compatible(other_type->return_type) ||
      param_types.size() != other_type->param_types.size()) {
    return false;
  }
  for (size_t i = 0; i < param_types.size(); i++) {
    if (!param_types[i]->compatible(other_type->param_types[i])) {
      return false;
    }
  }
  return true;
}
