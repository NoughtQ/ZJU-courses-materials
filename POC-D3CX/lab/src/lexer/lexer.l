%option noinput
%option nounput
%option noyywrap
%option yylineno

%{
#include "ast/tree.hpp"
#include "parser/parser.tab.hh"
#include <iostream>
#include <string>
#include <cstdlib>
extern FILE *input;
void yyerror(const char *s);
%}

digit [0-9]
blank [ \t\n\r]
letter [_a-zA-Z]
linecomment \/\/[^\n]*
comment \/\*([^*]|\*[^/])*\*\/
identifier {letter}({letter}|{digit})*

%%
  /* numbers */
"0"                { yylval.int_val = 0; return INTCONST; }
[1-9]{digit}*      { yylval.int_val = atoi(yytext); return INTCONST; }
0[0-7]+            { yylval.int_val = std::stoi(yytext, nullptr, 8); return INTCONST; }    // octal
0[xX][0-9a-fA-F]+  { yylval.int_val = std::stoi(yytext, nullptr, 16); return INTCONST; }    // hexadecimal

  /* arithmetic operators */
"+"             { return ADD; }
"-"             { return SUB; }
"*"             { return MUL; }
"/"             { return DIV; }
"%"             { return MOD; }

  /* relational operators */
"=="            { return EQ; }
"!="            { return NE; }
"<"             { return LT; }
">"             { return GT; }
"<="            { return LE; }
">="            { return GE; }

  /* logical operators */
"!"             { return NOT; }
"&&"            { return AND; }
"||"            { return OR; }

  /* seperators */
"("             { return LPAREN; }
")"             { return RPAREN; }
"["             { return LBRACK; }
"]"             { return RBRACK; }
"{"             { return LBRACE; }
"}"             { return RBRACE; }
"="             { return ASSIGN; }
","             { return COMMA; }
";"             { return SEMICOLON; }

  /* keywords */
"return"        { return RETURN; }
"int"           { return INT; }
"void"          { return VOID; }
"if"            { return IF; }
"else"          { return ELSE; }
"while"         { return WHILE; }
{identifier}    { yylval.str_val = strdup(yytext); return IDENT; }
{linecomment}   { }
{comment}       { }
{blank}         { }
.               { std::string msg = "unknown character '" + std::string(yytext) + "'"; yyerror(msg.c_str()); exit(1); }

%%
