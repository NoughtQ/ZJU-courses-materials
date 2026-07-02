#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

#include "analysis/cfg_builder.hpp"
#include "ast/tree.hpp"
#include "codegen/asm_emitter.hpp"
#include "codegen/inst_selector.hpp"
#include "codegen/reg_allocator.hpp"
#include "common.hpp"
#include "ir/ir_translator.hpp"
#include "semantic/type_checker.hpp"

extern int yydebug;  // 0: disable debug mode, 1: enable debug mode
extern int yyparse();
extern int yylex();
extern int yylineno;  // line number
extern FILE* yyin;
AST::NodePtr root;

class Argument {
 public:
  std::string input_file;
  std::string output_file;
  bool output_ir = false;
  bool use_venus = false;

  Argument(int argc, char** argv) {
    if (argc < 2) {
      throw std::runtime_error("Usage: " + std::string(argv[0]) +
                               " <input file> [output file] [--ir] [--venus]");
    }
    int pos = 1;
    for (int i = 1; i < argc; i++) {
      if (std::string(argv[i]) == "--ir") {
        output_ir = true;
      } else if (std::string(argv[i]) == "--venus") {
        use_venus = true;
      } else if (pos == 1) {
        input_file = argv[i];
        pos++;
      } else if (pos == 2) {
        output_file = argv[i];
        pos++;
      } else {
        throw std::runtime_error("No matching argument: " +
                                 std::string(argv[i]));
      }
    }
    if (output_ir && use_venus) {
      throw std::runtime_error(
          "Cannot output IR and Venus assembly at the same time");
    }
  }
};

int main(int argc, char** argv) {
  try {
    yylineno = 1;  // initialize line number

    Argument args(argc, argv);

    yyin = fopen(args.input_file.c_str(), "r");
    if (!yyin) {
      throw std::runtime_error(std::string("Cannot open file: ") + args.input_file);
    }

    // 输出 flex/bison 的调试信息
    // yydebug = 1;

    if (int parse_status = yyparse()) {
      throw CompileError(
          ErrorCode::SyntaxError,
          "Parse failed with status " + std::to_string(parse_status));
    }
    fclose(yyin);

    if (root) {
      std::ofstream output_file;
      if (!args.output_file.empty()) {
        output_file.open(args.output_file);
        if (!output_file.is_open()) {
          throw std::runtime_error("Cannot open output file: " +
                                   args.output_file);
        }
      }
      std::ostream& output = args.output_file.empty() ? std::cout : output_file;

      root->print_tree();
      std::cout << "Parse succeeded" << std::endl;

      auto type_checker = TypeChecker();
      type_checker.check(root);
      std::cout << "Semantic check passed" << std::endl;

      auto ir_translator = IRTranslator();
      auto ir = ir_translator.translate(root);
      std::cout << "IR generated" << std::endl;

      auto cfg_builder = CFGBuilder();
      auto mod = cfg_builder.build(ir);
      std::cout << "Control flow graph generated" << std::endl;

      if (args.output_ir) {
        output << mod.get_ir();
        return 0;
      }

      auto inst_selector = InstSelector();
      inst_selector.select(mod);
      std::cout << "Instruction selection done" << std::endl;

      auto reg_allocator = RegAllocator();
      reg_allocator.allocate(mod);
      std::cout << "Register allocation done" << std::endl;

      auto asm_emitter = ASMEmitter(args.use_venus, output);
      asm_emitter.emit(mod);
      std::cout << "Assembly generated" << std::endl;
    }

    return 0;
  } catch (const CompileError& e) {
    std::cerr << e.what() << std::endl;
    return static_cast<int>(e.code);
  } catch (const std::exception& e) {
    std::cerr << e.what() << std::endl;
    return 1;
  }
}
