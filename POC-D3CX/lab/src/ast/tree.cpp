#include "tree.hpp"

void AST::Node::print_tree(std::string prefix, std::string info_prefix) {
  std::cout << info_prefix << to_string() << " (line " << lineno << ")"
            << std::endl;
  auto children = get_children();
  if (children.size() == 1) {
    children[0]->print_tree(prefix + "    ", prefix + " └─ ");
  } else {
    for (size_t i = 0; i < children.size(); i++) {
      if (i == children.size() - 1) {
        children[i]->print_tree(prefix + "    ", prefix + " └─ ");
      } else {
        children[i]->print_tree(prefix + " │  ", prefix + " ├─ ");
      }
    }
  }
}
