# 问题1/2 文献下载清单（知网）

## 检索关键词

- 核心概念：无源定位、测向交叉定位、交会定位、方位角定位、示向度、测向定位
- 精度相关：定位精度、定位精度分析、误差椭圆、几何精度因子、GDOP、克拉美罗下界、CRLB、费舍尔信息矩阵
- 布站相关：布站、布站优化、观测站布局、站点布局、最优布站、传感器布局
- 算法相关：加权最小二乘、约束总体最小二乘、极大似然、泰勒级数展开、相位干涉仪

专业检索式（可直接粘贴）：

```
SU=('无源定位'+'测向交叉定位'+'方位角定位')*('精度'+'几何精度因子'+'GDOP')
SU=('测向交叉定位'+'交叉定位'+'交会定位')*('布站'+'观测站'+'布局优化'+'传感器布局')
SU=('交会角'+'定位区域'+'误差椭圆'+'几何精度因子')*('定位'+'测向'+'无源')
SU=('示向度'+'测向'+'方位角')*('误差'+'精度分析'+'定位算法')
SU=('双站'+'两站'+'单站')*('测向定位'+'交叉定位'+'定位精度')
SU=('加权最小二乘'+'最小二乘'+'极大似然'+'克拉美罗')*('测向'+'无源定位'+'交叉定位')
```

说明：链接为知网研学阅读页，登录后用页面顶部工具栏的「下载」图标取全文。数字为检索时的被引次数。

## A. 交会定位原理与定位精度（问题1 核心）

1. [不断发展的无源定位技术](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD2002&filename=HTDZ200201012&fileSourceType=1) — 被引 204
2. [辐射源无源定位研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CDFD&tablename=CDFD9908&filename=2000002525.nh&fileSourceType=1) — 被引 166
3. [多站时差定位技术研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD2003&filename=XDLD200302000&fileSourceType=1) — 被引 160
4. [基于运动学原理的单站无源定位与跟踪关键技术研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CDFD&tablename=CDFD9908&filename=2003097670.nh&fileSourceType=1) — 被引 145
5. [基于樽海鞘群算法的无源时差定位](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFDLAST2018&filename=DZYX201807010&fileSourceType=1) — 被引 111
6. [测向交叉定位系统中的交会角研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD2005&filename=YHXB200503008&fileSourceType=1) — 被引 109 ← 问题2 最直接的理论依据
7. [无源定位技术发展动态及其应用分析](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFDLAST2021&filename=HKBQ202102017&fileSourceType=1) — 被引 99
8. [空中观测平台对海面慢速目标单站无源定位跟踪及其关键技术研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CDFD&tablename=CDFD9908&filename=2003097701.nh&fileSourceType=1) — 被引 99
9. [无源定位技术研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD2006&filename=JCDZ200606004&fileSourceType=1) — 被引 81
10. [单站无源定位跟踪现有方法评述](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD2001&filename=HTDZ200106002&fileSourceType=1) — 被引 68
11. [无源定位技术研究及其定位精度分析](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CMFD&tablename=CMFD0506&filename=2005065010.nh&fileSourceType=1) — 被引 86
12. [无源定位及其定位性能的分析](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CMFD&tablename=CMFD9904&filename=2001007501.nh&fileSourceType=1) — 被引 46
13. [两站无源定位系统中的多目标跟踪算法研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD2002&filename=DZXU200212007&fileSourceType=1) — 被引 41

## B. 布站 / 观测点优化（问题2 核心）

14. [测向交叉定位最优布站方案分析](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD2014&filename=DZKK201408026&fileSourceType=1) — 被引 28 ← 与问题2 命题几乎一致
15. [无源定位优化布站分析研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CMFD&tablename=CMFD201402&filename=1014327754.nh&fileSourceType=1) — 被引 32
16. [测时差定位系统定位精度分析与最优布站](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD2003&filename=HKLD200301000&fileSourceType=1) — 被引 55
17. [多站无源定位精度分析及相关技术研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CMFD&tablename=CMFD2009&filename=2008122809.nh&fileSourceType=1) — 被引 53

## C. 定位解算算法（最小二乘 / 极大似然 / 泰勒展开）

18. [TDOA被动定位方法及精度分析](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD9899&filename=GFKJ802.011&fileSourceType=1) — 被引 115
19. [基于约束总体最小二乘方法的到达时差到达频差无源定位算法](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD2014&filename=DZYX201405010&fileSourceType=1) — 被引 96
20. [无源测向测时差定位算法研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD2003&filename=DZYX200306007&fileSourceType=1) — 被引 86
21. [利用频率变化率和波达角变化率单站无源定位与跟踪的关键技术研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CDFD&tablename=CDFD9908&filename=2005144413.nh&fileSourceType=1) — 被引 82
22. [基于角度信息的约束总体最小二乘无源定位算法](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD2006&filename=JEXK200608005&fileSourceType=1) — 被引 67
23. [运动多站无源定位关键技术研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CDFD&tablename=CDFD1214&filename=1012020167.nh&fileSourceType=1) — 被引 67
24. [基于TDOA和TOA的定位技术研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CMFD&tablename=CMFD201601&filename=1015433735.nh&fileSourceType=1) — 被引 65
25. [TDOA中的修正牛顿及泰勒级数方法](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFDLAST2017&filename=XDKD201606006&fileSourceType=1) — 被引 63
26. [基于时差频差的多站无源定位与跟踪算法研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CDFD&tablename=CDFDLAST2017&filename=1016247789.nh&fileSourceType=1) — 被引 53
27. [无源系统测向及时差频差联合定位方法研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CMFD&tablename=CMFD0506&filename=2005043164.nh&fileSourceType=1) — 被引 40
28. [基于TDOA/AOA的多站无源定位与跟踪算法研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CMFD&tablename=CMFD201902&filename=1019137440.nh&fileSourceType=1) — 被引 32
29. [无人机目标无源定位方法研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CMFD&tablename=CMFD201802&filename=1018708941.nh&fileSourceType=1) — 被引 30
30. [无人机高精度目标定位技术研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CMFD&tablename=CMFD201501&filename=1014061075.nh&fileSourceType=1) — 被引 50

## D. 测向设备与测角误差（问题1 中 ±1° 误差的现实来源）

31. [相位干涉仪测向定位研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD9899&filename=SHHT903.000&fileSourceType=1) — 被引 126
32. [基于相位干涉仪测向算法的定位技术研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CMFD&tablename=CMFD0506&filename=2006058326.nh&fileSourceType=1) — 被引 56
33. [基于中值滤波预处理的强冲击噪声背景测向方法](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFDLAST2021&filename=DZXU202106015&fileSourceType=1) — 被引 58

## E. 精度分析范式（方法可借鉴，非必须）

34. [浅海水声定位技术及应用研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CDFD&tablename=CDFD0911&filename=2008010975.nh&fileSourceType=1) — 被引 111
35. [北斗二代卫星导航系统定位精度分析方法研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CJFD&tablename=CJFD2009&filename=HYCH200901010&fileSourceType=1) — 被引 109
36. [非线性滤波方法在导航系统中的应用研究](https://ix.cnki.net/read/article/readonline?appid=CRSP_BASIC_PSMC&dbcode=CDFD&tablename=CDFD9908&filename=2005014471.nh&fileSourceType=1) — 被引 252

## 外文文献（种子）

- Dogançay K. Bearings-only target localization using total least squares. Signal Processing, 2005.
- Gavish M, Weiss A J. Performance analysis of bearing-only target location algorithms. IEEE Trans. AES, 1992.
- Torrieri D J. Statistical theory of passive location systems. IEEE Trans. AES, 1984.
- Van Trees H L. Detection, Estimation, and Modulation Theory (CRLB 与 Fisher 信息矩阵的标准参考).
- Martinez S, Bullo F. Optimal sensor placement and motion coordination for target tracking. Automatica, 2006.
