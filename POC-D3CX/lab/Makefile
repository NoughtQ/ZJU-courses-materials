CXX = g++
FLEX = flex
BISON = bison
CXXFLAGS = -std=c++17 -g -Wall -MMD -I$(SRC_DIR)
SRC_DIR = src

CFILES = $(shell find $(SRC_DIR) -name "*.c")
OBJS = $(CFILES:.c=.o)
CPPFILES = $(shell find $(SRC_DIR) -name "*.cpp")
OBJS += $(CPPFILES:.cpp=.o)
CCFILES = $(shell find $(SRC_DIR) -name "*.cc" | grep -v "\.\(yy\|tab\)\.cc$$")
OBJS += $(CCFILES:.cc=.o)  

LFILE = $(shell find $(SRC_DIR) -name "*.l")
YFILE = $(shell find $(SRC_DIR) -name "*.y")
LCCFILE = $(LFILE:.l=.yy.cc)
YCCFILE = $(YFILE:.y=.tab.cc)
YHEADER = $(YCCFILE:.cc=.hh)
LOBJ = $(LCCFILE:.cc=.o)
YOBJ = $(YCCFILE:.cc=.o)

DEPENDS = ${OBJS:.o=.d} $(LCCFILE:.cc=.d) $(YCCFILE:.cc=.d)

compiler: $(LOBJ) $(YOBJ) $(OBJS)
	$(CXX) -o $@ $^
	
-include ${DEPENDS}

$(YOBJ): $(YCCFILE)
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(YCCFILE) $(YHEADER): $(YFILE)
	$(BISON) -d -o $(YCCFILE) $^

$(LOBJ): $(LCCFILE)
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(LCCFILE): $(LFILE) $(YHEADER)
	$(FLEX) -o $@ $<

.PHONY: clean test format
clean:
	rm -f $(LCCFILE) $(YCCFILE) $(YHEADER)
	rm -f $(OBJS) $(LOBJ) $(YOBJ)
	rm -f $(DEPENDS)
	rm -f compiler

test:
	python3 sp26-tests/test.py $(shell git branch --show-current) .

format:
	find $(SRC_DIR) \( -name "*.cpp" -o -name "*.hpp" -o -name "*.def" \) | xargs clang-format -i