export const smtGlossary = [
  {
    keyword: 'declare-const',
    category: '声明',
    description: '声明一个常量符号及其类型，适合把自然语言中的变量映射到求解器上下文。',
    example: '(declare-const x Int)',
  },
  {
    keyword: 'declare-fun',
    category: '声明',
    description: '声明函数或谓词签名，不给出函数体，适合表示抽象关系。',
    example: '(declare-fun P (Int) Bool)',
  },
  {
    keyword: 'assert',
    category: '约束',
    description: '把一个公式加入约束集，是将自然语言条件落地为 SMT 约束的核心命令。',
    example: '(assert (> x 0))',
  },
  {
    keyword: 'check-sat',
    category: '求解',
    description: '要求求解器判断当前约束集是否可满足，典型返回为 sat、unsat 或 unknown。',
    example: '(check-sat)',
  },
  {
    keyword: 'get-model',
    category: '求解',
    description: '在 sat 时读取一个满足约束的模型，便于前端展示变量取值和反例。',
    example: '(get-model)',
  },
  {
    keyword: 'and / or / not',
    category: '布尔连接',
    description: '对应逻辑与、逻辑或、逻辑非，可把自然语言中的复合条件组合成公式。',
    example: '(assert (and (> x 0) (< x 10)))',
  },
  {
    keyword: '=>',
    category: '蕴含',
    description: '表示逻辑蕴含，适合表达“如果……那么……”这一类待证性质。',
    example: '(assert (=> (> x 5) (> x 0)))',
  },
  {
    keyword: 'forall / exists',
    category: '量词',
    description: '分别表示全称量词和存在量词，常见于程序验证、定理证明和规约描述。',
    example: '(assert (forall ((x Int)) (>= (* x x) 0)))',
  },
  {
    keyword: 'push / pop',
    category: '上下文',
    description: '保存与回退求解上下文，适合前端做“假设切换”“分支比较”“历史试探”。',
    example: '(push 1)\n(assert (= x 5))\n(pop 1)',
  },
  {
    keyword: '∀ ∃ ⇒ ∧ ∨ ¬',
    category: '符号',
    description: '这些是常见的形式化验证符号。前端已使用适合数学符号与等宽代码的字体回退链展示它们。',
    example: '∀x. P(x)  ∃y. Q(y)  A ⇒ B  A ∧ B  A ∨ B  ¬A',
  },
]
