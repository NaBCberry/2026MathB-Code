# -*- coding: utf-8 -*-
"""把论文里 ``\\subsubsection{算法版本对照与负结果}`` 整段替换成基于 8500 局实测的新版。

只做两件事（都可回滚，先写 .bak-<时间戳> 备份）：

1. 把三张图从 ``docs/figs/`` 拷到 tex 同目录（LaTeX 里用中文文件名引用，与现有图一致）；
2. 用新写的段落替换旧段落（从 ``\\subsubsection{算法版本对照与负结果}`` 起，
   到下一个 ``% =====`` 分节注释之前）。

    python tools/insert_p4_versions.py --dry-run     # 只看将要写入的内容，不动文件
    python tools/insert_p4_versions.py               # 真正写入
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

TEX = Path(r"D:\2026cumcm\docs\Latex\无线电干扰源的快速自动定位与清除.tex")
FIG_SRC = Path(r"D:\2026cumcm\codes\docs\figs")
FIG_MAP = {
    "p4_box.png": "问题4算法分布箱线图.png",
    "p4_hist.png": "问题4算法分布叠加.png",
    "p4_tradeoff.png": "问题4速度完备性取舍.png",
}
START_MARK = r"\subsubsection{算法版本对照与负结果}"
END_PREFIX = "% ===="

# 同时把第三题那张旧表（100 例 / 50 例）刷新成 8500 局评测里的新数字，
# 否则本节正文引用的"2000 局 / 1000 局"会与那张表自相矛盾。
TEXT_FIXES = [
    (r"\caption{问题 3 离线演练结果（统一案例数）}",
     r"\caption{问题 3 离线演练结果（同一批种子；末行为问题 4 环境反面对照）}"),
    (r"\texttt{p3-baseline}（主算法） & 100 & 100\% & 315.8 & 108.9 \\",
     r"\texttt{p3-baseline}（主算法） & 2000 & 100\% & 314.6 & 109.2 \\"),
    (r"\texttt{p3-wxm-fast}（对照） & 1000 & 100\% & 366.9 & 133.5 \\",
     r"\texttt{p3-v2}（对照） & 1000 & 100\% & 366.9 & 133.5 \\"),
    (r"\texttt{p3-baseline} 跑问题 4 环境（反面对照） & 50 & 74\% & 437 & 124.0 \\",
     r"\texttt{p3-baseline} 跑问题 4 环境（反面对照） & 500 & 77.9\% & 438.5 & 126.5 \\"),
]

NEW = r"""\subsubsection{算法版本对照与负结果}
\label{sec:p4-versions}

\textbf{（1）评测协议。}所有版本在同一台机器、同一套离线模拟器
（\texttt{archived/mock\_arena.py}，与正式测试同规则）上评测：同一题内各版本使用
\textbf{同一批随机种子}，因此可以逐局配对比较；每局指标按题目定义取
“该局定位清除总时间 $\div$ 该局被清除的干扰源个数”。
样本量为：主算法与对照算法各 $2000$ 局（两个互不重叠的种子批次 $1\sim1000$ 与
$10001\sim11000$，用于检验跨种子稳定性），其余版本各 $500$ 局。
统计量同时给出均值、标准差、中位数、$p_{90}$ 与最坏值——实测分布明显右偏
（图 \ref{fig:p4-version-box}），少数难例把均值抬高，只报均值会掩盖尾部。

\textbf{（2）版本对照。}

\begin{table}[H]\centering
\footnotesize
\caption{问题 4 各算法离线演练对照（同一批种子；$2000$ 例者为两批不重叠种子合并）}
\label{tab:p4-versions}
\resizebox{\linewidth}{!}{%
\begin{tabular}{lcccccccc}
\toprule
版本 & 例数 & 清除比例 & 全清局占比 & 均值/s & 标准差 & 中位数/s & $p_{90}$/s & measure 次数 \\
\midrule
\texttt{p4-directional}（v1） & 500 & 99.94\% & 99.20\% & 648.4 & 92.8 & 640.5 & 780.8 & 298.0 \\
\texttt{p4-v2-receding}（v2） & 500 & 99.93\% & 99.20\% & 605.3 & 94.1 & 597.9 & 741.0 & 306.5 \\
\texttt{p4-v3-residual}（v3） & 500 & 99.93\% & 99.20\% & 605.3 & 94.1 & 597.9 & 741.2 & 306.5 \\
\texttt{p4-v4-ring1950}（v4） & 500 & 99.95\% & 99.40\% & 620.0 & 96.5 & 612.8 & 761.2 & 307.1 \\
\texttt{p4-v5-ring1930}（v5） & 500 & 99.93\% & 99.20\% & 613.0 & 94.8 & 607.0 & 751.0 & 306.1 \\
\texttt{p4-v6-policy}（v6） & 500 & 99.94\% & 99.20\% & 579.0 & 95.3 & 573.6 & 718.9 & 307.3 \\
\texttt{p4-v7-stationgate}（v7） & 500 & \textbf{100\%} & \textbf{100\%} & 569.9 & 95.2 & 562.1 & 709.6 & 311.0 \\
\texttt{p4-v8-geoorder}（v8，主算法） & 2000 & \textbf{100\%} & \textbf{100\%} & \textbf{567.6} & 93.5 & 554.2 & 703.8 & 309.7 \\
\bottomrule
\end{tabular}}
\end{table}
\note{“清除比例”是各局（清除个数 $\div$ 源个数）的均值，“全清局占比”是一局一个不漏的比例；
两者含义不同，前者对“只漏一个源”不敏感，故一并列出；
表中每个版本都由逐局结果（\texttt{bench/} 下的 CSV）汇总而来，可复现。}

\begin{figure}[H]\centering
\includegraphics[width=0.72\linewidth]{问题4算法分布箱线图.png}
\caption{问题 4 各版本平均定位清除时间的分布（箱体为四分位区间，红菱形为均值，
蓝横线为中位数，灰点为单局结果）。版本链自左向右单调改善；
横轴标签的第二行给出全清局占比，只有 v7、v8 达到 $100\%$。}
\label{fig:p4-version-box}
\end{figure}

\begin{figure}[H]\centering
\includegraphics[width=0.68\linewidth]{问题4算法分布叠加.png}
\caption{问题 4 四个主力版本（v2／v6／v7／v8）平均定位清除时间的直方图与核密度估计。
v6 起整条分布明显左移；v6 与 v8 的差别主要在右尾——v6 的最坏值达 $933.9$ s，
v8 为 $883.7$ s。}
\label{fig:p4-version-hist}
\end{figure}

\begin{figure}[H]\centering
\includegraphics[width=0.72\linewidth]{问题4速度完备性取舍.png}
\caption{问题 4 的“速度—完备性”取舍图（左上更好）。v8 同时取得最小均值与 $100\%$ 全清局占比；
v4、v5 想用更远的布站换稳健性，结果既没有更快，全清局占比也没有回到 $100\%$。}
\label{fig:p4-version-tradeoff}
\end{figure}

\textbf{（3）结论。}三点。

\textbf{其一，速度单调改进且尾部队列一致前移。}平均定位清除时间自 v1 的 $648.4$ s
降到 v2 的 $605.3$ s、v6 的 $579.0$ s，再到 v8 的 $567.6$ s，相对 v1 缩短 $12.5\%$；
中位数同步从 $640.5$ s 降到 $554.2$ s，$p_{90}$ 从 $780.8$ s 降到 $703.8$ s，
说明改进发生在整条分布上，不是少数极端例被削掉。

\textbf{其二，只有 v7、v8 守住了“确保全部清除”。}v1$\sim$v6 的全清局占比都是
$99.2\%\sim99.4\%$（$500$ 局中有 $3\sim4$ 局漏掉一个源），
而 v7（$500$ 局）与 v8（$2000$ 局）均为 $100\%$。二者的增益来自两处：
一是\textbf{测站补测闸门}（v7）——测站上的扫描不再只服务“发现”，
对已发现但未清除的频道，若“区域到该站的最小距离 $\le1500$ m”
且“最坏读数下的新误差界至少降低 $35\%$”，就在该站顺手补测一条方位线；
二是\textbf{几何站优先}（v8）——逼近卡住时，把“能砍掉至少一半误差界”的测站
在调度代价上减秒，先去把它测掉。代价是每局多约 $2.4$ 次 measure
（$309.7$ 对 v2 的 $306.5$），远低于它省下的行驶时间。

\textbf{其三，跨种子稳定。}主算法两个独立种子批次分别为 $569.0$ s（种子 $1\sim1000$）
与 $566.2$ s（种子 $10001\sim11000$），相差 $0.5\%$；第三题主算法两批为
$314.4$ s 与 $314.7$ s。问题 3 的对照结论同向：\texttt{p3-baseline}（$2000$ 局，
$314.6$ s）比对照版本 \texttt{p3-v2}（$1000$ 局，$366.9$ s）快 $14.2\%$，
且平均 measure 次数更少（$109.2$ 对 $133.5$），
说明“顺路扫频 + 动态布点”这类为提速而生的改动在这套代价结构下并不提速
（见表 \ref{tab:p3-results}）。

\textbf{（4）负结果。}表 \ref{tab:p4-negative} 汇总了被实测否决的改动。
列出它们有两个作用：一是说明当前版本不是“拍参数”拍出来的，
每条路径都有实测数字；二是给后续改进划出已排除的方向。

{\scriptsize
\setlength{\tabcolsep}{4pt}
\begin{longtable}{>{\raggedright\arraybackslash}p{0.30\linewidth}
                  >{\raggedright\arraybackslash}p{0.28\linewidth}
                  >{\raggedright\arraybackslash}p{0.34\linewidth}}
\caption{被实测否决的改动（负结果）}
\label{tab:p4-negative}\\
\toprule
尝试的改动 & 实测结果 & 否决原因 \\
\midrule
\endfirsthead
\multicolumn{3}{l}{\footnotesize 续表 \thetable\ ——被实测否决的改动}\\
\toprule
尝试的改动 & 实测结果 & 否决原因 \\
\midrule
\endhead
\bottomrule
\endlastfoot
宽角优先补测（把 $\pm40^\circ$ 排到共线点之前） & 清除瞬间误差界 $\le20$ m 的比例
$48\%\to84\%$、落空 /clear 从 $9.6$ 降到 $2.2$ 次/局，但总时间 $7906\to8108$ s
（$+2.6\%$），清除比例 $100\%\to99.92\%$ & 一次测量只值 $6$ s，
为取得 $60^\circ\sim90^\circ$ 交会角要多绕 $0.4d$ 的横向路程（$d=1500$ m 时约 $600$ m $=120$ s），
顺路多测几次共线点更省 \\
\midrule
预测误差界排序候选点（\texttt{predict\_order}） & $656$ s 对 $628$ s（$24$ 例） &
候选点里多数“指向估计点”的楔形与细长区域不相交，预测值退化为 $\infty$，排序塌成“就近优先” \\
\midrule
收尾代价权重（\texttt{lockin\_weight}） & $677.5$ s（$24$ 例） &
写成“整个频道剩余时间”等于强迫先巡完再统一清除，里程反而贵约 $38\%$；
改成两步前瞻仍略负 \\
\midrule
冗余罚 / 奖励共享（\texttt{redundancy\_penalty}） & $722.4$ s（$24$ 例） &
把机器狗推离了本来需要复测的位置；文献里的奖励共享建立在栅格概率地图上，
搬成“近邻罚时”过于粗糙 \\
\midrule
机会主义执行（\texttt{opportunity\_m} $=200/400/700/1200$ m） &
$7952/7965/7925/8419$ s（默认 $7545$ s） &
收尾时最后一段路是“免费”的（跑完即结束、不必回主线），
提前做要花去 + 回两程，本结构下推迟反而更省 \\
\midrule
固定巡回序 + 走廊规则（\texttt{backbone}，走廊 $150/250/500$ m 与无限走廊） &
$8536/8440/8395/8663$ s（默认 $7897$ s） &
超额里程不是排序造成的，而是每个频道 $3\sim4$ 次逼近测量本身固有的 \\
\midrule
新发现就地优先（\texttt{fresh\_bonus} $=80/150/250/400$ s） &
$631.6/637.2/640.3/642.2$ s（$0$ 时 $585.4$ s），$150$ s 时还丢完备性 &
软排序一样会打乱 $25$ 站普查路线，而漏源代价不可接受 \\
\midrule
同心螺旋站序 & 开放路径 $18.55$ km 对最近邻 $+$ 2-opt 的 $18.42$ km &
相差不到 $1\%$，换序无收益 \\
\midrule
外环减站（\texttt{outer\_k} $=8$，$21$ 站） & 省约 $10\%$ 时间，清除比例 $-0.12\%$ &
直接违反“确保所有干扰源被清除”，否决 \\
\midrule
外环外扩到 $1950/1930$ m（v4／v5） & $620.0/613.0$ s，全清局占比 $99.4\%/99.2\%$ &
既没有更快，也没有换来 $100\%$ 全清——完备性的瓶颈不在外环半径 \\
\midrule
残余集合优化（v3） & $500$ 例中仅 $1$ 例与 v2 不同（种子 $277$：$741.1$ 对 $750.5$ s） &
残余频道平均不足 $1$ 个，开关基本不触发；保留 v2 为主算法，
v3 只作为“为何不能再压”的检验证据 \\
\midrule
v8 的“无条件几何绕站”（\texttt{geo\_trigger\_stuck}$=0$） &
减项 $40/80/150$ s 分别为 $569.8/592.0/604.4$ s（v7 基准 $569.9$ s） &
减项打在 $25$ 个普查任务之一上，无条件打折会把机器狗拽离滚动 TSP 主线；
“几何被锁死”是约 $1/300$ 的稀有事件，故改为“逼近卡住才绕” \\
\end{longtable}}

\note{负结果同样有正面价值：表 \ref{tab:p4-negative} 中“宽角优先”一项说明
本环境中\textbf{几何指标最优 $\ne$ 总时间最优}——多站交会能把保证误差界压到
$20$ m 以内，但为此付出的横向绕行远贵于顺路多测几次；
这一条与问题二“第二检测点取约 $90^\circ$ 交会角”是两回事：
问题二只算定位精度，不计行驶代价。}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = TEX.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    try:
        start = next(i for i, l in enumerate(lines) if l.strip().startswith(START_MARK))
    except StopIteration:
        print("[错误] 找不到 " + START_MARK)
        return 2
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith(END_PREFIX)), len(lines))
    print("将替换第 %d~%d 行（共 %d 行），新内容 %d 行"
          % (start + 1, end, end - start, NEW.count("\n")))
    if args.dry_run:
        print("--- 新内容前 12 行 ---")
        print(nl.join(NEW.split("\n")[:12]))
        print("--- 新内容末 4 行 ---")
        print(nl.join(NEW.rstrip("\n").split("\n")[-4:]))
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(TEX, TEX.with_suffix(".tex.bak-" + stamp))
    for src, dst in FIG_MAP.items():
        s = FIG_SRC / src
        if not s.exists():
            print("[警告] 缺图 " + str(s))
            continue
        shutil.copy2(s, TEX.parent / dst)
        print("拷图 %s → %s" % (src, dst))
    new_lines = NEW.rstrip("\n").split("\n")
    out = nl.join(lines[:start] + new_lines + lines[end:])
    for old, new in TEXT_FIXES:
        n = out.count(old)
        print(("  [%d 处] " % n) + old[:60])
        out = out.replace(old, new)
    TEX.write_bytes(out.encode("utf-8"))
    print("已写入 %s（备份 .tex.bak-%s）" % (TEX.name, stamp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
