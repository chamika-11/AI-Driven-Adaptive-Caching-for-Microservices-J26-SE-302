# T3 - head-to-head statistics (post-hoc family, Addendum S1)

| agent | capacity | mean dU vs place_size:p25 | Cohen d_z | Wilcoxon p | Holm p |
|---|---|---|---|---|---|
| dqn:main | 0.0100 | -0.0020 | -0.0727 | 0.4316 | 1.0000 |
| dqn:main | 0.0500 | -0.0769 | -1.0734 | 0.0020 | 0.0293 |
| dqn:main | 0.2500 | -0.0758 | -1.2929 | 0.0020 | 0.0293 |
| dqn:bandit | 0.0100 | -0.0140 | -0.5107 | 0.1602 | 0.6543 |
| dqn:bandit | 0.0500 | -0.0376 | -1.2857 | 0.0039 | 0.0352 |
| dqn:bandit | 0.2500 | -0.0330 | -0.6760 | 0.0195 | 0.1367 |
| dqn:vanilla | 0.0100 | -0.0198 | -0.8383 | 0.0273 | 0.1641 |
| dqn:vanilla | 0.0500 | -0.0850 | -1.0306 | 0.0020 | 0.0293 |
| dqn:vanilla | 0.2500 | -0.0797 | -1.2891 | 0.0020 | 0.0293 |
| tabq:qbin | 0.0100 | 0.0017 | 0.1246 | 0.9219 | 1.0000 |
| tabq:qbin | 0.0500 | -0.0440 | -1.5707 | 0.0039 | 0.0352 |
| tabq:qbin | 0.2500 | -0.2913 | -1.2725 | 0.0020 | 0.0293 |
| tabq:bandit | 0.0100 | -0.0062 | -0.4182 | 0.4316 | 1.0000 |
| tabq:bandit | 0.0500 | -0.0524 | -1.6306 | 0.0020 | 0.0293 |
| tabq:bandit | 0.2500 | -0.0177 | -0.5802 | 0.1309 | 0.6543 |

Test slice, evaluation seeds 0-9, synthetic. Negative dU = agent worse than the size-threshold placement rule.
