#ifndef ANALYSIS_CFG_BUILDER_HPP
#define ANALYSIS_CFG_BUILDER_HPP

#include "analysis/control_flow.hpp"

class CFGBuilder {
 public:
  Module build(IR::Code code);

 private:
  FunctionPtr build_single_func(IR::Code code);
  std::string new_label();
};

#endif  // ANALYSIS_CFG_BUILDER_HPP