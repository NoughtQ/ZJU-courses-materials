#ifndef COMMON_HPP
#define COMMON_HPP

#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

// 基本类型枚举
enum class BasicType { Unknown, Int, Void };
inline constexpr const char* type_to_string(BasicType type) {
  switch (type) {
    case BasicType::Unknown:
      return "unknown";
    case BasicType::Int:
      return "int";
    case BasicType::Void:
      return "void";
  }
  return "unknown";
}

// 二元运算符枚举
enum class BinaryOp { 
  Add, Sub, Mul, Div, Mod, 
  Eq, Ne, Lt, Gt, Le, Ge, 
  And, Or
};
inline constexpr const char* op_to_string(BinaryOp op) {
  switch (op) {
    case BinaryOp::Add:
      return "+";
    case BinaryOp::Sub:
      return "-";
    case BinaryOp::Mul:
      return "*";
    case BinaryOp::Div:
      return "/";
    case BinaryOp::Mod:
      return "%";
    case BinaryOp::Eq:
      return "==";
    case BinaryOp::Ne:
      return "!=";
    case BinaryOp::Lt:
      return "<";
    case BinaryOp::Gt:
      return ">";
    case BinaryOp::Le:
      return "<=";
    case BinaryOp::Ge:
      return ">=";
    case BinaryOp::And:
      return "&&";
    case BinaryOp::Or:
      return "||";
  }
  return "unknown";
}

// 一元运算符枚举
enum class UnaryOp { Pos, Neg, Not };
inline constexpr const char* op_to_string(UnaryOp op) {
  switch (op) {
    case UnaryOp::Pos:
      return "+";
    case UnaryOp::Neg:
      return "-";
    case UnaryOp::Not:
      return "!";
  }
  return "unknown";
}

// use C++ RTTI to check the type of a shared_ptr
template <typename T, typename U>
inline bool type_of(const std::shared_ptr<U>& node) {
  return std::dynamic_pointer_cast<T>(node) != nullptr;
}

#define ASSERT(expr, msg)                                                \
  do {                                                                   \
    if (!(expr)) {                                                       \
      std::cerr << "Assertion failed at " << __FILE__ << ":" << __LINE__ \
                << " (" << #expr << "): " << msg << std::endl;           \
      std::exit(1);                                                      \
    }                                                                    \
  } while (0)

// Error codes for compiler diagnostics
enum class ErrorCode {
  OK = 0,
  SyntaxError = 1,
  NotAssignable = 2,
  ExcessInitializers = 3,
  IncompatibleConversion = 4,
  InvalidOperands = 5,
  NotSubscriptable = 6,
  ReturnMismatch = 7,
  NotIntegerSubscript = 8,
  NotCallable = 9,
  Undeclared = 10,
  Redefinition = 11,
  InvalidInitializer = 12,
  ArityMismatch = 13,
};

inline constexpr const char* error_to_string(ErrorCode code) {
  switch (code) {
    case ErrorCode::OK:
      return "OK";
    case ErrorCode::SyntaxError:
      return "Syntax Error";
    case ErrorCode::NotAssignable:
      return "Not Assignable";
    case ErrorCode::ExcessInitializers:
      return "Excess Initializers";
    case ErrorCode::IncompatibleConversion:
      return "Incompatible Conversion";
    case ErrorCode::InvalidOperands:
      return "Invalid Operands";
    case ErrorCode::NotSubscriptable:
      return "Not Subscriptable";
    case ErrorCode::ReturnMismatch:
      return "Return Mismatch";
    case ErrorCode::NotIntegerSubscript:
      return "Not Integer Subscript";
    case ErrorCode::NotCallable:
      return "Not Callable";
    case ErrorCode::Undeclared:
      return "Undeclared";
    case ErrorCode::Redefinition:
      return "Redefinition";
    case ErrorCode::InvalidInitializer:
      return "Invalid Initializer";
    case ErrorCode::ArityMismatch:
      return "Arity Mismatch";
  }
  return "Unknown Error";
}

class CompileError : public std::runtime_error {
 public:
  ErrorCode code;
  CompileError(ErrorCode code)
      : std::runtime_error(error_to_string(code)), code(code) {}
  CompileError(ErrorCode code, const std::string& msg)
      : std::runtime_error(msg), code(code) {}
};

#endif  // COMMON_HPP