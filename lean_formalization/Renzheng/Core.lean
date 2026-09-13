/-
  2026 国赛 B 题《无线电干扰源的快速自动定位与清除》
  ——论文中已写好的数学命题的 Lean 4 形式化核验（Lean v4.33.0 + Mathlib）

  * 平面取复平面 `ℂ`（即欧氏平面 ℝ²），`dist` 为欧氏距离；
  * 每条定理的注释注明对应论文位置（式号 / 小节）；
  * 外部文献结论（Jung 定理）显式声明为 `axiom`，其余为完整证明；
  * 与论文原文口径不一致或需补加假设处，注释中以【口径】/【缺条件】标出。
-/
import Mathlib

noncomputable section
open Complex
open scoped Real

namespace Renzheng

/-! ## 0. 平面几何基本记号 -/

/-- 平面上的点：欧氏平面 ℝ² 取为复平面。 -/
abbrev Pt : Type := ℂ

/-- 二维点积。 -/
def dot (z w : Pt) : ℝ := z.re * w.re + z.im * w.im

/-- 二维叉积（有向面积）。 -/
def cross (z w : Pt) : ℝ := z.re * w.im - z.im * w.re

/-- 单位方向向量 (cos θ, sin θ)。 -/
def dir (θ : ℝ) : Pt := ⟨Real.cos θ, Real.sin θ⟩

lemma dot_comm (z w : Pt) : dot z w = dot w z := by
  simp only [dot]; ring

lemma dot_sub_left (x p n : Pt) : dot (x - p) n = dot x n - dot p n := by
  simp only [dot, Complex.sub_re, Complex.sub_im]; ring

lemma dot_i (z w : Pt) : dot (z * I) w = cross z w := by
  simp only [dot, cross]
  rw [Complex.mul_I_re, Complex.mul_I_im]
  ring

/-- 点积作为 ℝ-线性函数 `z ↦ ⟪z, n⟫`。 -/
def dotL (n : Pt) : Pt →ₗ[ℝ] ℝ where
  toFun := fun z => dot z n
  map_add' := by
    intro x y
    simp only [dot, Complex.add_re, Complex.add_im]; ring
  map_smul' := by
    intro r x
    simp only [dot, Complex.smul_re, Complex.smul_im, smul_eq_mul, RingHom.id_apply]
    ring

@[simp] lemma dotL_apply (n z : Pt) : dotL n z = dot z n := rfl

lemma dist_sq (z w : Pt) : dist z w ^ 2 = dot (z - w) (z - w) := by
  rw [Complex.dist_eq, ← Complex.normSq_eq_norm_sq, Complex.normSq_apply, dot,
    Complex.sub_re, Complex.sub_im]
  try ring

lemma dist_sq_eq (z w : Pt) :
    dist z w ^ 2 = (z.re - w.re) ^ 2 + (z.im - w.im) ^ 2 := by
  rw [dist_sq]
  simp only [dot, Complex.sub_re, Complex.sub_im]
  try ring

lemma dist_eq_sqrt (z w : Pt) :
    dist z w = Real.sqrt ((z.re - w.re) ^ 2 + (z.im - w.im) ^ 2) := by
  have h : dist z w = Real.sqrt (dist z w ^ 2) := by
    rw [Real.sqrt_sq_eq_abs, abs_of_nonneg dist_nonneg]
  rw [h, dist_sq_eq]

lemma eq_of_sq_eq_of_nonneg {x y : ℝ} (hx : 0 ≤ x) (hy : 0 ≤ y) (h : x ^ 2 = y ^ 2) : x = y := by
  have h1 : x = Real.sqrt (x ^ 2) := by rw [Real.sqrt_sq_eq_abs, abs_of_nonneg hx]
  have h2 : y = Real.sqrt (y ^ 2) := by rw [Real.sqrt_sq_eq_abs, abs_of_nonneg hy]
  rw [h1, h2, h]

/-- 二维 Cauchy–Schwarz。 -/
lemma abs_dot_le (z w : Pt) : |dot z w| ≤ ‖z‖ * ‖w‖ := by
  have hsq : dot z w ^ 2 ≤ (‖z‖ * ‖w‖) ^ 2 := by
    rw [mul_pow, ← Complex.normSq_eq_norm_sq, ← Complex.normSq_eq_norm_sq,
      Complex.normSq_apply, Complex.normSq_apply, dot]
    nlinarith [sq_nonneg (z.re * w.im - z.im * w.re)]
  calc |dot z w| = Real.sqrt (dot z w ^ 2) := (Real.sqrt_sq_eq_abs _).symm
    _ ≤ Real.sqrt ((‖z‖ * ‖w‖) ^ 2) := Real.sqrt_le_sqrt hsq
    _ = ‖z‖ * ‖w‖ := by
        rw [Real.sqrt_sq_eq_abs, abs_of_nonneg (mul_nonneg (norm_nonneg _) (norm_nonneg _))]

/-! ## 1. 问题一：定位区域是凸集、直径与最小外接圆 -/

/-- 闭半平面 `{x | 0 ≤ ⟪x - p, n⟫}`。 -/
def halfPlaneGE (p n : Pt) : Set Pt := {x | 0 ≤ dot (x - p) n}

/-- 闭半平面 `{x | ⟪x - p, n⟫ ≤ 0}`。 -/
def halfPlaneLE (p n : Pt) : Set Pt := {x | dot (x - p) n ≤ 0}

lemma halfPlaneGE_eq (p n : Pt) : halfPlaneGE p n = (dotL n) ⁻¹' (Set.Ici (dot p n)) := by
  ext x
  simp only [halfPlaneGE, Set.mem_setOf_eq, Set.mem_preimage, Set.mem_Ici, dotL_apply]
  rw [dot_sub_left]
  constructor <;> intro h <;> linarith

lemma halfPlaneLE_eq (p n : Pt) : halfPlaneLE p n = (dotL n) ⁻¹' (Set.Iic (dot p n)) := by
  ext x
  simp only [halfPlaneLE, Set.mem_setOf_eq, Set.mem_preimage, Set.mem_Iic, dotL_apply]
  rw [dot_sub_left]
  constructor <;> intro h <;> linarith

lemma convex_halfPlaneGE (p n : Pt) : Convex ℝ (halfPlaneGE p n) := by
  rw [halfPlaneGE_eq p n]
  exact (convex_Ici (dot p n)).linear_preimage (dotL n)

lemma convex_halfPlaneLE (p n : Pt) : Convex ℝ (halfPlaneLE p n) := by
  rw [halfPlaneLE_eq p n]
  exact (convex_Iic (dot p n)).linear_preimage (dotL n)

/-- 第 i 个检测点的检测楔形：两条边界射线（`φ-δ` 与 `φ+δ`）之间的闭楔形。 -/
def wedge (s : Pt) (φ δ : ℝ) : Set Pt :=
  halfPlaneGE s (dir (φ - δ) * I) ∩ halfPlaneLE s (dir (φ + δ) * I)

lemma convex_wedge (s : Pt) (φ δ : ℝ) : Convex ℝ (wedge s φ δ) :=
  (convex_halfPlaneGE s (dir (φ - δ) * I)).inter
    (convex_halfPlaneLE s (dir (φ + δ) * I))

/-- 【论文式 (eq:p1-region)】定位区域 `P = (⋂ᵢ Wᵢ) ∩ C_{R_T}` 是凸集。 -/
theorem localizationRegion_convex {ι : Type*} (W : ι → Set Pt)
    (hW : ∀ i, Convex ℝ (W i)) (c : Pt) (R : ℝ) :
    Convex ℝ ((⋂ i, W i) ∩ Metric.closedBall c R) :=
  (convex_iInter hW).inter (convex_closedBall c R)

/-- 问题一的具体形态：N 个检测楔形 ∩ 目标圆域。 -/
theorem localizationRegion_convex_of_wedges {ι : Type*} (S : ι → Pt) (φ δ : ι → ℝ) :
    Convex ℝ ((⋂ i, wedge (S i) (φ i) (δ i)) ∩ Metric.closedBall (0 : Pt) 1800) :=
  localizationRegion_convex _ (fun i => convex_wedge _ _ _) _ _

/-- 【论文 §1.2】包含 S 的半径 R 圆盘 ⟹ S 中任意两点距离 ≤ 2R。 -/
theorem dist_le_two_mul_radius {S : Set Pt} {c : Pt} {R : ℝ}
    (h : S ⊆ Metric.closedBall c R) :
    ∀ x ∈ S, ∀ y ∈ S, dist x y ≤ 2 * R := by
  intro x hx y hy
  have hx' : dist x c ≤ R := Metric.mem_closedBall.mp (h hx)
  have hy' : dist y c ≤ R := Metric.mem_closedBall.mp (h hy)
  calc dist x y ≤ dist x c + dist c y := dist_triangle x c y
    _ = dist x c + dist y c := by rw [dist_comm c y]
    _ ≤ R + R := add_le_add hx' hy'
    _ = 2 * R := by ring

/-- 最小外接圆（最小包围圆）。 -/
def IsMEC (S : Set Pt) (c : Pt) (R : ℝ) : Prop :=
  S ⊆ Metric.closedBall c R ∧ ∀ c' R', S ⊆ Metric.closedBall c' R' → R ≤ R'

/--
【外部定理，论文 ref26：Jung 1901】平面 Jung 定理（作为公设引入，未在 Lean 中证明）。
-/
axiom jung_plane (S : Set Pt) (D : ℝ) (hD : 0 ≤ D)
    (hdiam : ∀ x ∈ S, ∀ y ∈ S, dist x y ≤ D) :
    ∃ c : Pt, S ⊆ Metric.closedBall c (D / Real.sqrt 3)

/-- 【论文式 (eq:p1-jung)】`D/2 ≤ R_c ≤ D/√3`（`hDmax`：直径在两点处取到）。 -/
theorem mec_bounds {S : Set Pt} {c : Pt} {R D : ℝ} (hM : IsMEC S c R)
    (hD : 0 ≤ D) (hdiam : ∀ x ∈ S, ∀ y ∈ S, dist x y ≤ D)
    (hDmax : ∃ x ∈ S, ∃ y ∈ S, dist x y = D) :
    D / 2 ≤ R ∧ R ≤ D / Real.sqrt 3 := by
  obtain ⟨x, hx, y, hy, hxy⟩ := hDmax
  have h1 : D ≤ 2 * R := by
    have := dist_le_two_mul_radius hM.1 x hx y hy
    linarith
  have h2 : R ≤ D / Real.sqrt 3 := by
    obtain ⟨c', hc'⟩ := jung_plane S D hD hdiam
    exact hM.2 c' (D / Real.sqrt 3) hc'
  exact ⟨by linarith, h2⟩

/-! ### 1.1 反例：等边三角形（论文 §1.3、图 `jung反例.png`） -/

/-- 第三个顶点 ω = (1/2, √3/2)。 -/
def ω : Pt := ⟨1 / 2, Real.sqrt 3 / 2⟩

/-- 等边三角形顶点集（边长 1，直径 1）。 -/
def eqTri : Set Pt := {0, 1, ω}

/-- 等边三角形的外心。 -/
def circum : Pt := ⟨1 / 2, Real.sqrt 3 / 6⟩

lemma circum_re : circum.re = 1 / 2 := rfl
lemma circum_im : circum.im = Real.sqrt 3 / 6 := rfl

/-- 竖直向下的点 (0, -t)（用于构造内点之外的见证点）。 -/
def down (t : ℝ) : Pt := ⟨0, -t⟩

lemma down_re (t : ℝ) : (down t).re = 0 := rfl
lemma down_im (t : ℝ) : (down t).im = -t := rfl

lemma sqrt3_sq : Real.sqrt 3 ^ 2 = 3 := Real.sq_sqrt (by norm_num)
lemma sqrt3_pos : 0 < Real.sqrt 3 := Real.sqrt_pos_of_pos (by norm_num)
lemma mem_eqTri_zero : (0 : Pt) ∈ eqTri := by simp [eqTri]
lemma mem_eqTri_one : (1 : Pt) ∈ eqTri := by simp [eqTri]
lemma mem_eqTri_ω : ω ∈ eqTri := by simp [eqTri]

lemma dist_zero_one : dist (0 : Pt) (1 : Pt) = 1 := by
  rw [dist_eq_sqrt]; norm_num

lemma dist_zero_ω : dist (0 : Pt) ω = 1 := by
  rw [dist_eq_sqrt]
  simp only [ω, Complex.zero_re, Complex.zero_im, Complex.sub_re, Complex.sub_im]
  have h : (0 - 1 / 2 : ℝ) ^ 2 + (0 - Real.sqrt 3 / 2) ^ 2 = 1 := by
    nlinarith [sqrt3_sq]
  rw [h, Real.sqrt_one]

lemma dist_one_ω : dist (1 : Pt) ω = 1 := by
  rw [dist_eq_sqrt]
  simp only [ω, Complex.one_re, Complex.one_im, Complex.sub_re, Complex.sub_im,
    Complex.zero_re, Complex.zero_im]
  have h : (1 - 1 / 2 : ℝ) ^ 2 + (0 - Real.sqrt 3 / 2) ^ 2 = 1 := by
    nlinarith [sqrt3_sq]
  rw [h, Real.sqrt_one]

/-- 三个顶点两两距离 ≤ 1。 -/
lemma dist_eqTri_le_one : ∀ x ∈ eqTri, ∀ y ∈ eqTri, dist x y ≤ 1 := by
  intro x hx y hy
  simp only [eqTri, Set.mem_insert_iff, Set.mem_singleton_iff] at hx hy
  rcases hx with rfl | rfl | rfl <;> rcases hy with rfl | rfl | rfl
  all_goals first
    | (rw [dist_self]; norm_num)
    | exact le_of_eq dist_zero_one
    | exact le_of_eq dist_zero_ω
    | exact le_of_eq dist_one_ω
    | exact le_of_eq (by rw [dist_comm]; exact dist_zero_one)
    | exact le_of_eq (by rw [dist_comm]; exact dist_zero_ω)
    | exact le_of_eq (by rw [dist_comm]; exact dist_one_ω)

/-- 到三顶点距离平方和：`= 3(u-1/2)² + 3(v-√3/6)² + 1 ≥ 1`。 -/
lemma sum_sq_dist_eqTri (c : Pt) :
    dist c 0 ^ 2 + dist c 1 ^ 2 + dist c ω ^ 2
      = 3 * (c.re - 1 / 2) ^ 2 + 3 * (c.im - Real.sqrt 3 / 6) ^ 2 + 1 := by
  rw [dist_sq_eq, dist_sq_eq, dist_sq_eq]
  simp only [ω, Complex.zero_re, Complex.zero_im, Complex.one_re, Complex.one_im]
  nlinarith [sqrt3_sq]

/-- 任意包含等边三角形的圆盘半径 ≥ 1/√3。 -/
lemma radius_ge_of_contains_eqTri (c : Pt) (r : ℝ)
    (h : eqTri ⊆ Metric.closedBall c r) : 1 / Real.sqrt 3 ≤ r := by
  have h0 : dist c 0 ≤ r := by
    have := Metric.mem_closedBall.mp (h mem_eqTri_zero)
    rwa [dist_comm] at this
  have h1 : dist c 1 ≤ r := by
    have := Metric.mem_closedBall.mp (h mem_eqTri_one)
    rwa [dist_comm] at this
  have hw : dist c ω ≤ r := by
    have := Metric.mem_closedBall.mp (h mem_eqTri_ω)
    rwa [dist_comm] at this
  have hr : 0 ≤ r := le_trans dist_nonneg h0
  have hsum : dist c 0 ^ 2 + dist c 1 ^ 2 + dist c ω ^ 2 ≤ 3 * r ^ 2 := by
    have a : dist c 0 ^ 2 ≤ r ^ 2 := by
      nlinarith [dist_nonneg (x := c) (y := (0 : Pt)), h0, hr]
    have b : dist c 1 ^ 2 ≤ r ^ 2 := by
      nlinarith [dist_nonneg (x := c) (y := (1 : Pt)), h1, hr]
    have d : dist c ω ^ 2 ≤ r ^ 2 := by
      nlinarith [dist_nonneg (x := c) (y := ω), hw, hr]
    linarith
  rw [sum_sq_dist_eqTri] at hsum
  have hge : (1 : ℝ) ≤ 3 * r ^ 2 := by
    nlinarith [sq_nonneg (c.re - 1 / 2), sq_nonneg (c.im - Real.sqrt 3 / 6)]
  have h3 : (1 : ℝ) / 3 ≤ r ^ 2 := by linarith
  have hs13 : Real.sqrt ((1 : ℝ) / 3) = 1 / Real.sqrt 3 := by
    rw [Real.sqrt_div (by norm_num : (0 : ℝ) ≤ 1) 3, Real.sqrt_one]
  have hsr : Real.sqrt ((1 : ℝ) / 3) ≤ r := (Real.sqrt_le_iff).mpr ⟨hr, h3⟩
  rwa [hs13] at hsr

lemma sqrt3_lt_two : Real.sqrt 3 < 2 := by
  have h : Real.sqrt 3 < Real.sqrt 4 := Real.sqrt_lt_sqrt (by norm_num) (by norm_num)
  rwa [show (4 : ℝ) = 2 ^ 2 by norm_num, Real.sqrt_sq_eq_abs,
    abs_of_nonneg (by norm_num : (0 : ℝ) ≤ 2)] at h

/-- 论文"直径圆不保证覆盖"的最小反例：等边三角形（D = 1，D/2 圆盖不住）。 -/
theorem equilateral_not_covered_by_half :
    ¬ ∃ c : Pt, eqTri ⊆ Metric.closedBall c (1 / 2 : ℝ) := by
  rintro ⟨c, hc⟩
  have hge := radius_ge_of_contains_eqTri c (1 / 2) hc
  have hlt : (1 : ℝ) / 2 < 1 / Real.sqrt 3 := by
    have hsq : ((1 : ℝ) / 2) ^ 2 < (1 / Real.sqrt 3) ^ 2 := by
      have h3 : (1 / Real.sqrt 3 : ℝ) ^ 2 = 1 / 3 := by
        rw [div_pow, one_pow, sqrt3_sq]
      rw [h3, div_pow, one_pow]; norm_num
    have h := sq_lt_sq.mp hsq
    rwa [abs_of_nonneg (by norm_num : (0 : ℝ) ≤ 1 / 2),
      abs_of_nonneg (by positivity : (0 : ℝ) ≤ 1 / Real.sqrt 3)] at h
  linarith

/-- 外心到三个顶点的距离都等于 1/√3。 -/
lemma dist_circum_eq (v : Pt) (hv : v ∈ eqTri) :
    dist circum v = 1 / Real.sqrt 3 := by
  simp only [eqTri, Set.mem_insert_iff, Set.mem_singleton_iff] at hv
  have hsq1 : (1 / Real.sqrt 3 : ℝ) ^ 2 = ((1 : ℝ) / 3) := by
    rw [div_pow, one_pow, sqrt3_sq]
  apply eq_of_sq_eq_of_nonneg dist_nonneg (by positivity)
  rw [dist_sq_eq, hsq1, circum_re, circum_im]
  rcases hv with rfl | rfl | rfl
  · simp only [Complex.zero_re, Complex.zero_im]
    nlinarith [sqrt3_sq]
  · simp only [Complex.one_re, Complex.one_im]
    nlinarith [sqrt3_sq]
  · simp only [ω]
    nlinarith [sqrt3_sq]

/-- 等边三角形的最小外接圆半径恰为 1/√3（外心 (1/2, √3/6)）。 -/
theorem equilateral_mec : IsMEC eqTri circum (1 / Real.sqrt 3) := by
  constructor
  · intro x hx
    rw [Metric.mem_closedBall, dist_comm]
    exact le_of_eq (dist_circum_eq x hx)
  · intro c' R' hc'
    exact radius_ge_of_contains_eqTri c' R' hc'

/-- 【论文问题一结论】"以定位区域直径为直径的圆不保证覆盖该区域"。 -/
theorem diameter_disk_does_not_cover :
    ∃ S : Set Pt, (∀ x ∈ S, ∀ y ∈ S, dist x y ≤ 1) ∧
      ¬ ∃ c : Pt, S ⊆ Metric.closedBall c (1 / 2 : ℝ) :=
  ⟨eqTri, dist_eqTri_le_one, equilateral_not_covered_by_half⟩

/-! ### 1.2 【口径】"最小外接圆圆心必落在 P 的内部"——应修正为"落在 P 内" -/

/-- 顶点 -1、1、i 构成的直角三角形。 -/
def rightTri : Set Pt := {-1, 1, I}

lemma dist_zero_neg_one : dist (0 : Pt) (-1) = 1 := by
  rw [dist_eq_sqrt]; norm_num

lemma dist_zero_I : dist (0 : Pt) I = 1 := by
  rw [dist_eq_sqrt]
  simp only [Complex.zero_re, Complex.zero_im, Complex.sub_re, Complex.sub_im,
    Complex.I_re, Complex.I_im]
  norm_num

/-- 顶点 -1、1、i 的最小外接圆是单位圆（圆心 0）；而 0 位于斜边 -1→1 上（边界）。 -/
theorem rightTri_mec : IsMEC rightTri 0 1 := by
  constructor
  · intro x hx
    simp only [rightTri, Set.mem_insert_iff, Set.mem_singleton_iff] at hx
    rw [Metric.mem_closedBall]
    rcases hx with rfl | rfl | rfl
    · rw [dist_comm]; exact le_of_eq dist_zero_neg_one
    · rw [dist_comm]; exact le_of_eq dist_zero_one
    · rw [dist_comm]; exact le_of_eq dist_zero_I
  · intro c' R' hc'
    have h1 : dist (-1 : Pt) (1 : Pt) ≤ 2 * R' :=
      dist_le_two_mul_radius hc' (-1) (by simp [rightTri]) 1 (by simp [rightTri])
    have h2 : dist (-1 : Pt) (1 : Pt) = 2 := by
      rw [dist_eq_sqrt]; norm_num
    linarith

theorem rightTri_convexHull_subset_upper :
    convexHull ℝ rightTri ⊆ {x : Pt | 0 ≤ x.im} := by
  have hset : ({x : Pt | 0 ≤ x.im} : Set Pt) = halfPlaneGE 0 I := by
    ext x
    simp only [Set.mem_setOf_eq, halfPlaneGE, dot, Complex.sub_re, Complex.sub_im,
      Complex.zero_re, Complex.zero_im, Complex.I_re, Complex.I_im]
    ring_nf
  rw [hset]
  refine convexHull_min ?_ (convex_halfPlaneGE 0 I)
  intro x hx
  simp only [rightTri, Set.mem_insert_iff, Set.mem_singleton_iff] at hx
  rcases hx with rfl | rfl | rfl <;>
    simp only [halfPlaneGE, Set.mem_setOf_eq, dot, Complex.sub_re, Complex.sub_im,
      Complex.zero_re, Complex.zero_im, Complex.I_re, Complex.I_im] <;>
    norm_num

/-- 0 的任意小邻域内都有 P 之外的点 ⟹ 0 不是 P 的内点。 -/
theorem mec_center_boundary_witness :
    ∀ ε > 0, ∃ z : Pt, dist z 0 < ε ∧ z ∉ convexHull ℝ rightTri := by
  intro ε hε
  refine ⟨down (ε / 2), ?_, ?_⟩
  · rw [dist_eq_sqrt]
    simp only [down_re, down_im, Complex.sub_re, Complex.sub_im, Complex.zero_re,
      Complex.zero_im]
    have hsq : (0 - 0 : ℝ) ^ 2 + (-(ε / 2) - 0) ^ 2 = (ε / 2) ^ 2 := by ring
    rw [hsq, Real.sqrt_sq_eq_abs, abs_of_nonneg (by linarith : (0 : ℝ) ≤ ε / 2)]
    linarith
  · intro hz
    have hmem := rightTri_convexHull_subset_upper hz
    simp only [Set.mem_setOf_eq, down_im] at hmem
    linarith

/-- 但 0 确实属于 P（它是斜边中点），故 0 是 P 的**边界点**而非外点：
论文的 "内部" 应改为 "内（含边界）"。 -/
theorem zero_mem_convexHull_rightTri : (0 : Pt) ∈ convexHull ℝ rightTri := by
  have h1 : (-1 : Pt) ∈ convexHull ℝ rightTri :=
    subset_convexHull ℝ _ (by simp [rightTri])
  have h2 : (1 : Pt) ∈ convexHull ℝ rightTri :=
    subset_convexHull ℝ _ (by simp [rightTri])
  have hc := convex_convexHull ℝ rightTri
  have hmem := hc h1 h2 (by norm_num : (0 : ℝ) ≤ 1 / 2) (by norm_num : (0 : ℝ) ≤ 1 / 2)
    (by norm_num : (1 : ℝ) / 2 + 1 / 2 = 1)
  simpa using hmem

/-! ## 2. 问题二：一阶线性化、R_c 闭式与"一次清除"临界距离 -/

/-- 第二个检测点 (a,b) 到源的距离 r₂。 -/
def r2 (r a b : ℝ) : ℝ := Real.sqrt ((r - a) ^ 2 + b ^ 2)

lemma r2_sq (r a b : ℝ) : r2 r a b ^ 2 = (r - a) ^ 2 + b ^ 2 :=
  Real.sq_sqrt (by positivity)

lemma r2_nonneg (r a b : ℝ) : 0 ≤ r2 r a b := Real.sqrt_nonneg _

/-- 【论文式 (eq:p2-shift)】一阶扰动方程的解（Δx 与 Δs 的定义式满足两个分量方程）。 -/
theorem p2_shift_solution {r a b s1 s2 ρ : ℝ} (hb : b ≠ 0) (hρ : ρ ≠ 0)
    (hρ2 : ρ ^ 2 = (r - a) ^ 2 + b ^ 2) :
    (ρ ^ 2 * s2 - r * (r - a) * s1) / b
        = b * s2 + (ρ * ((r - a) * s2 - r * s1) / b) * (r - a) / ρ
      ∧ r * s1 - (r - a) * s2 + (ρ * ((r - a) * s2 - r * s1) / b) * b / ρ = 0 := by
  constructor
  · rw [hρ2]; field_simp; ring
  · field_simp; ring

/-- 【论文式 (eq:p2-diag) 核心】两条半对角线长度取大者。 -/
theorem p2_max_diag {r a b ρ : ℝ} (hr : 0 ≤ r) (hρ2 : ρ ^ 2 = (r - a) ^ 2 + b ^ 2) :
    max (Real.sqrt (a ^ 2 + b ^ 2)) (Real.sqrt ((2 * r - a) ^ 2 + b ^ 2))
      = Real.sqrt (r ^ 2 + ρ ^ 2 + 2 * r * |r - a|) := by
  rcases le_total a r with h | h
  · have habs : |r - a| = r - a := abs_of_nonneg (by linarith)
    have h1 : a ^ 2 + b ^ 2 = r ^ 2 + ρ ^ 2 - 2 * r * (r - a) := by nlinarith [hρ2]
    have h2 : (2 * r - a) ^ 2 + b ^ 2 = r ^ 2 + ρ ^ 2 + 2 * r * (r - a) := by
      nlinarith [hρ2]
    have hle : Real.sqrt (a ^ 2 + b ^ 2)
        ≤ Real.sqrt ((2 * r - a) ^ 2 + b ^ 2) := by
      apply Real.sqrt_le_sqrt
      nlinarith [mul_nonneg hr (sub_nonneg.mpr h)]
    rw [max_eq_right hle, h2, habs]
  · have habs : |r - a| = a - r := by rw [abs_of_nonpos (sub_nonpos.mpr h)]; ring
    have h1 : a ^ 2 + b ^ 2 = r ^ 2 + ρ ^ 2 + 2 * r * (a - r) := by nlinarith [hρ2]
    have h2 : (2 * r - a) ^ 2 + b ^ 2 = r ^ 2 + ρ ^ 2 - 2 * r * (a - r) := by
      nlinarith [hρ2]
    have hle : Real.sqrt ((2 * r - a) ^ 2 + b ^ 2) ≤ Real.sqrt (a ^ 2 + b ^ 2) := by
      apply Real.sqrt_le_sqrt
      nlinarith [mul_nonneg hr (sub_nonneg.mpr h)]
    rw [max_eq_left hle, h1, habs]

/-- 【论文式 (eq:p2-rc-form)】乘上公共因子 `tanδ·ρ/|b|` 后即得 R_c 闭式。 -/
theorem p2_Rc_formula {r a b ρ δ : ℝ} (hr : 0 ≤ r) (hρ : 0 ≤ ρ) (htan : 0 ≤ Real.tan δ)
    (hρ2 : ρ ^ 2 = (r - a) ^ 2 + b ^ 2) :
    max (Real.tan δ * (ρ / |b|) * Real.sqrt (a ^ 2 + b ^ 2))
        (Real.tan δ * (ρ / |b|) * Real.sqrt ((2 * r - a) ^ 2 + b ^ 2))
      = Real.tan δ * (ρ / |b|) * Real.sqrt (r ^ 2 + ρ ^ 2 + 2 * r * |r - a|) := by
  have hc : 0 ≤ Real.tan δ * (ρ / |b|) :=
    mul_nonneg htan (div_nonneg hρ (abs_nonneg _))
  have hAB := p2_max_diag hr hρ2
  rcases le_total (Real.sqrt (a ^ 2 + b ^ 2)) (Real.sqrt ((2 * r - a) ^ 2 + b ^ 2)) with h | h
  · have hB : Real.sqrt ((2 * r - a) ^ 2 + b ^ 2)
        = Real.sqrt (r ^ 2 + ρ ^ 2 + 2 * r * |r - a|) := by
      rw [← hAB, max_eq_right h]
    rw [max_eq_right (mul_le_mul_of_nonneg_left h hc), hB]
  · have hA : Real.sqrt (a ^ 2 + b ^ 2) = Real.sqrt (r ^ 2 + ρ ^ 2 + 2 * r * |r - a|) := by
      rw [← hAB, max_eq_left h]
    rw [max_eq_left (mul_le_mul_of_nonneg_left h hc), hA]

/-- `ρ/|b| ≥ 1`。 -/
lemma one_le_rho_div_abs {r a b ρ : ℝ} (hb : b ≠ 0) (hρ : 0 ≤ ρ)
    (hρ2 : ρ ^ 2 = (r - a) ^ 2 + b ^ 2) :
    1 ≤ ρ / |b| := by
  have hbpos : 0 < |b| := abs_pos.mpr hb
  have hle : |b| ≤ ρ := by
    have h2 : |b| ^ 2 ≤ ρ ^ 2 := by rw [hρ2, sq_abs]; nlinarith [sq_nonneg (r - a)]
    have := sq_le_sq.mp h2
    rwa [abs_of_nonneg (abs_nonneg b), abs_of_nonneg hρ] at this
  rw [le_div_iff₀ hbpos]
  rw [one_mul]
  exact hle

/-- 【论文式 (eq:p2-lower)】`R_c ≥ r·tanδ`。 -/
theorem p2_Rc_lower {r a b ρ δ : ℝ} (hr : 0 ≤ r) (hρ : 0 ≤ ρ) (hb : b ≠ 0)
    (hρ2 : ρ ^ 2 = (r - a) ^ 2 + b ^ 2) (htan : 0 ≤ Real.tan δ) :
    r * Real.tan δ
      ≤ Real.tan δ * (ρ / |b|) * Real.sqrt (r ^ 2 + ρ ^ 2 + 2 * r * |r - a|) := by
  have hcoef : 0 ≤ ρ / |b| := div_nonneg hρ (abs_nonneg _)
  have hone := one_le_rho_div_abs (r := r) hb hρ hρ2
  have hS : r ≤ Real.sqrt (r ^ 2 + ρ ^ 2 + 2 * r * |r - a|) := by
    have hsq : r ^ 2 ≤ r ^ 2 + ρ ^ 2 + 2 * r * |r - a| := by
      nlinarith [sq_nonneg ρ, mul_nonneg hr (abs_nonneg (r - a))]
    have := Real.sqrt_le_sqrt hsq
    rwa [Real.sqrt_sq_eq_abs, abs_of_nonneg hr] at this
  have h1 : r ≤ ρ / |b| * Real.sqrt (r ^ 2 + ρ ^ 2 + 2 * r * |r - a|) := by
    calc r = 1 * r := (one_mul r).symm
      _ ≤ (ρ / |b|) * r := by
          exact mul_le_mul_of_nonneg_right hone hr
      _ ≤ (ρ / |b|) * Real.sqrt (r ^ 2 + ρ ^ 2 + 2 * r * |r - a|) :=
          mul_le_mul_of_nonneg_left hS hcoef
  calc r * Real.tan δ ≤ (ρ / |b| * Real.sqrt (r ^ 2 + ρ ^ 2 + 2 * r * |r - a|)) * Real.tan δ :=
        mul_le_mul_of_nonneg_right h1 htan
    _ = Real.tan δ * (ρ / |b|) * Real.sqrt (r ^ 2 + ρ ^ 2 + 2 * r * |r - a|) := by ring

/-- 【论文式 (eq:p2-1146) 的结构形式】`R_c ≤ 20 ⟹ r ≤ 20/tanδ`。 -/
theorem p2_threshold_necessary {r a b ρ δ : ℝ} (hr : 0 ≤ r) (hρ : 0 ≤ ρ) (hb : b ≠ 0)
    (hρ2 : ρ ^ 2 = (r - a) ^ 2 + b ^ 2) (htan : 0 < Real.tan δ)
    (h20 : Real.tan δ * (ρ / |b|) * Real.sqrt (r ^ 2 + ρ ^ 2 + 2 * r * |r - a|) ≤ 20) :
    r ≤ 20 / Real.tan δ := by
  have h := p2_Rc_lower hr hρ hb hρ2 (le_of_lt htan)
  have : r * Real.tan δ ≤ 20 := le_trans h h20
  rw [le_div_iff₀ htan]
  linarith

/-- 论文中的数值 1146 的来源：tanδ ≈ 0.017455 时 `20/tanδ ≈ 1146`。 -/
theorem p2_threshold_numeric {δ : ℝ} (h1 : (0.0174 : ℝ) < Real.tan δ)
    (h2 : Real.tan δ < (0.0176 : ℝ)) :
    1136 < 20 / Real.tan δ ∧ 20 / Real.tan δ < 1150 := by
  have hpos : 0 < Real.tan δ := by linarith
  constructor
  · rw [lt_div_iff₀ hpos]; nlinarith
  · rw [div_lt_iff₀ hpos]; nlinarith

/-- 论文式 (eq:p2-rightangle)：直角交会时 η = (4/π)·rb/(r²+b²) 的最大值 2/π（AM–GM）。 -/
theorem p2_eta_max (r b : ℝ) (hr : 0 < r) (hb : 0 < b) :
    4 * r * b / (Real.pi * (r ^ 2 + b ^ 2)) ≤ 2 / Real.pi := by
  have hpi : 0 < Real.pi := Real.pi_pos
  have hden : 0 < Real.pi * (r ^ 2 + b ^ 2) := by positivity
  rw [div_le_iff₀ hden]
  have h : (2 / Real.pi) * (Real.pi * (r ^ 2 + b ^ 2)) = 2 * (r ^ 2 + b ^ 2) := by
    field_simp
  rw [h]
  nlinarith [sq_nonneg (r - b)]

/-- 论文 §3.4 的精化步长 `u = min{max{R_c,1}, max{950-R_c,100}}`。 -/
def refineStep (Rc : ℝ) : ℝ := min (max Rc 1) (max (950 - Rc) 100)

/-- 【缺条件】精化步长并不保证 `u ≥ R_c`：`R_c > 475` 时会取到第二支。 -/
theorem refineStep_lt (Rc : ℝ) (h1 : 475 < Rc) (h2 : 100 ≤ Rc) : refineStep Rc < Rc := by
  have hmax1 : max Rc 1 = Rc := max_eq_left (by linarith)
  have hmax2 : max (950 - Rc) 100 < Rc := max_lt (by linarith) (by linarith)
  simp only [refineStep, hmax1]
  exact min_lt_iff.mpr (Or.inr hmax2)

/-- 具体反例：`R_c = 900` 时 `u = 100 < R_c`，且 `u + R_c = 1000 > 950`。 -/
theorem refineStep_counterexample : refineStep 900 = 100 ∧ 950 < refineStep 900 + 900 := by
  constructor <;> norm_num [refineStep]

/-- 【补条件后的正面结论】若 `R_c ≤ 850`，则 `u + R_c ≤ 950`（补测点仍能收到信号）。 -/
theorem refineStep_add_le (Rc : ℝ) (h : Rc ≤ 850) : refineStep Rc + Rc ≤ 950 := by
  have hmax : max (950 - Rc) 100 = 950 - Rc := max_eq_left (by linarith)
  have hle : refineStep Rc ≤ 950 - Rc := by
    simp only [refineStep, hmax]
    exact min_le_right _ _
  linarith

/-! ## 3. 问题三：覆盖判据的充分性与布站覆盖半径 -/

/--
【论文式 (eq:cover)】覆盖判据的充分性：若目标区域内每一点都被"无信号测站"的
`R_min` 圆盘覆盖，则该频道不存在未清除干扰源。

* `R`：有效接收半径（≥ `R_min`）；
* `hDetect`：物理假设"距离不超过接收半径 ⇒ 该处必收到信号"；
* `hNoSignal`：这些测站读数为 `no_signal`。
-/
theorem cover_criterion_sound (Target : Set Pt) (Sc : Set Pt) (Source : Pt → Prop)
    (R : Pt → ℝ) (Rmin : ℝ) (Detect : Pt → Pt → Prop)
    (hInTarget : ∀ G, Source G → G ∈ Target)
    (hCover : ∀ G ∈ Target, ∃ s ∈ Sc, dist s G ≤ Rmin)
    (hRmin : ∀ G, Source G → Rmin ≤ R G)
    (hDetect : ∀ s G, dist s G ≤ R G → Detect s G)
    (hNoSignal : ∀ s ∈ Sc, ∀ G, Source G → ¬ Detect s G) :
    ∀ G, ¬ Source G := by
  intro G hG
  obtain ⟨s, hs, hsd⟩ := hCover G (hInTarget G hG)
  exact hNoSignal s hs G hG (hDetect s G (le_trans hsd (hRmin G hG)))

/-! ## 3. 问题四：包围条件（凸包判据）、边界点与最少测站数 -/

/--
【论文式 (eq:p4-hull) 的充分性证明】若 `p = Σ αᵢ vᵢ`（αᵢ ≥ 0，Σαᵢ = 1）是 `A(p)` 中
测站的凸组合，且每个测站都满足 `⟪vᵢ - p, u⟫ < 0`（即全部落在以 `u` 为法向的开半平面内），
则矛盾：凸组合必落在同一开半平面内，而 `⟪p - p, u⟫ = 0`。

这正是论文"conv(A(p)) ⊆ 开半平面，而 p 在边界上"的推理。
-/
theorem hull_criterion_sound {ι : Type*} [Fintype ι] (v : ι → Pt) (α : ι → ℝ) (p u : Pt)
    (hα : ∀ i, 0 ≤ α i) (hsum : ∑ i, α i = 1) (hp : p = ∑ i, α i • v i)
    (hneg : ∀ i, dot (v i - p) u < 0) : False := by
  have hpos : 0 < ∑ i, α i := by rw [hsum]; norm_num
  obtain ⟨i₀, _, hi₀⟩ := (Finset.sum_pos_iff_of_nonneg (fun i _ => hα i)).mp hpos
  have hlin : dot p u = ∑ i, α i * dot (v i) u := by
    show dotL u p = ∑ i, α i * dot (v i) u
    rw [hp, map_sum]
    simp only [map_smul, dotL_apply, smul_eq_mul]
  have hzero : ∑ i, α i * dot (v i - p) u = 0 := by
    have hterm : ∀ i, α i * dot (v i - p) u = α i * dot (v i) u - α i * dot p u := by
      intro i; rw [dot_sub_left]; ring
    calc ∑ i, α i * dot (v i - p) u
        = ∑ i, (α i * dot (v i) u - α i * dot p u) :=
          Finset.sum_congr rfl (fun i _ => hterm i)
      _ = (∑ i, α i * dot (v i) u) - (∑ i, α i) * dot p u := by
          rw [Finset.sum_sub_distrib, Finset.sum_mul]
      _ = dot p u - 1 * dot p u := by rw [hlin, hsum]
      _ = 0 := by ring
  have hlt : (∑ i : ι, α i * dot (v i - p) u) < (∑ _i : ι, (0 : ℝ)) := by
    refine Finset.sum_lt_sum (s := (Finset.univ : Finset ι)) ?_ ⟨i₀, Finset.mem_univ _, ?_⟩
    · intro i _
      exact mul_nonpos_of_nonneg_of_nonpos (hα i) (le_of_lt (hneg i))
    · have := mul_neg_of_pos_of_neg hi₀ (hneg i₀); simpa using this
  simp only [Finset.sum_const_zero] at hlt
  linarith

/-- 【论文 §4.1 边界结论】若 A(p) 的测站全在圆域内部，则边界点 p 不在 conv(A(p)) 中。 -/
theorem boundary_point_not_in_convexHull {A : Set Pt} {p : Pt} {RT : ℝ}
    (hA : A ⊆ Metric.ball 0 RT) (hp : dist p 0 = RT) :
    p ∉ convexHull ℝ A := by
  intro hpconv
  have hsub : convexHull ℝ A ⊆ Metric.ball (0 : Pt) RT := convexHull_min hA (convex_ball 0 RT)
  have hmem := hsub hpconv
  have hlt : dist p 0 < RT := Metric.mem_ball.mp hmem
  linarith

/-- 望远镜求和：`Σ_{i<k} (a(i+1) - a i) = a k - a 0`。 -/
lemma sum_range_telescope (f : ℕ → ℝ) (n : ℕ) :
    ∑ i ∈ Finset.range n, (f (i + 1) - f i) = f n - f 0 := by
  induction n with
  | zero => simp
  | succ n ih => rw [Finset.sum_range_succ, ih]; ring

/--
【论文式 (eq:p4-gap) → (eq:p4-kmin)】把 k 个方位角排在圆周上（`a` 单调、`a k = a 0 + 2π`），
则相邻间隔（含首尾环绕段）必有一段 ≥ 360°/k。
-/
theorem gap_pigeonhole (k : ℕ) (hk : 0 < k) (a : ℕ → ℝ)
    (hmono : ∀ i, i < k → a i ≤ a (i + 1)) (hwrap : a k = a 0 + 2 * Real.pi) :
    ∃ i, i < k ∧ 2 * Real.pi / k ≤ a (i + 1) - a i := by
  by_contra hcon
  push_neg at hcon
  have hsum : ∑ i ∈ Finset.range k, (a (i + 1) - a i) = 2 * Real.pi := by
    rw [sum_range_telescope, hwrap]; ring
  have hlt : ∑ i ∈ Finset.range k, (a (i + 1) - a i)
      < ∑ i ∈ Finset.range k, (2 * Real.pi / k) := by
    refine Finset.sum_lt_sum ?_ ⟨0, Finset.mem_range.mpr hk, hcon 0 hk⟩
    intro i hi
    exact le_of_lt (hcon i (Finset.mem_range.mp hi))
  rw [hsum, Finset.sum_const, Finset.card_range, nsmul_eq_mul] at hlt
  have hkne : (k : ℝ) ≠ 0 := by exact_mod_cast Nat.pos_iff_ne_zero.mp hk
  have hk' : (k : ℝ) * (2 * Real.pi / k) = 2 * Real.pi := by field_simp
  rw [hk'] at hlt
  exact lt_irrefl _ hlt

/-- 【论文式 (eq:p4-kmin)】围住一点所需最少测站数：`π/β ≤ k`（即 ⌈180°/β⌉）。 -/
theorem kmin_le (k : ℕ) (hk : 0 < k) (a : ℕ → ℝ) (β : ℝ) (hβ : 0 < β)
    (hmono : ∀ i, i < k → a i ≤ a (i + 1)) (hwrap : a k = a 0 + 2 * Real.pi)
    (hgap : ∀ i, i < k → a (i + 1) - a i ≤ 2 * β) :
    Real.pi / β ≤ k := by
  obtain ⟨i, hi, hge⟩ := gap_pigeonhole k hk a hmono hwrap
  have h1 : 2 * Real.pi / k ≤ 2 * β := le_trans hge (hgap i hi)
  have hkpos : (0 : ℝ) < k := by exact_mod_cast hk
  have h2 : 2 * Real.pi ≤ 2 * β * k := (div_le_iff₀ hkpos).mp h1
  rw [div_le_iff₀ hβ]
  nlinarith

/--
【论文 §4.5 三角覆盖判据】`p` 落在三顶点（任意有限多个测站）的凸包内、且任意两顶点
距离 ≤ R，则每个顶点到 p 的距离都 ≤ R（即所有顶点都落在 `A(p)` 中）。
-/
theorem triangle_cover_criterion {ι : Type*} [Fintype ι] (v : ι → Pt) (α : ι → ℝ) (p : Pt)
    (hα : ∀ i, 0 ≤ α i) (hsum : ∑ i, α i = 1) (hp : p = ∑ i, α i • v i)
    (R : ℝ) (hR : ∀ i j, dist (v i) (v j) ≤ R) :
    ∀ i, dist p (v i) ≤ R := by
  intro i
  have hdecomp : p - v i = ∑ j, α j • (v j - v i) := by
    calc p - v i = (∑ j, α j • v j) - (∑ j, α j) • v i := by rw [hp, hsum, one_smul]
      _ = (∑ j, α j • v j) - ∑ j, α j • v i := by rw [Finset.sum_smul]
      _ = ∑ j, (α j • v j - α j • v i) := by rw [Finset.sum_sub_distrib]
      _ = ∑ j, α j • (v j - v i) := by
          exact Finset.sum_congr rfl (fun j _ => by rw [smul_sub])
  calc dist p (v i) = ‖p - v i‖ := dist_eq_norm _ _
    _ = ‖∑ j, α j • (v j - v i)‖ := by rw [hdecomp]
    _ ≤ ∑ j, ‖α j • (v j - v i)‖ := norm_sum_le _ _
    _ = ∑ j, α j * ‖v j - v i‖ := by
        refine Finset.sum_congr rfl (fun j _ => ?_)
        rw [norm_smul, Real.norm_of_nonneg (hα j)]
    _ ≤ ∑ j, α j * R := by
        refine Finset.sum_le_sum (fun j _ => ?_)
        refine mul_le_mul_of_nonneg_left ?_ (hα j)
        rw [← dist_eq_norm]; exact hR j i
    _ = R := by rw [← Finset.sum_mul, hsum, one_mul]

/-- 【论文式 (eq:p4-tangent)】外切条件 `ρ·cos(π/n) > R_T ⟺ ρ > R_T/cos(π/n)`。 -/
theorem tangent_condition {ρ RT c : ℝ} (hc : 0 < c) :
    RT < ρ * c ↔ RT / c < ρ := by
  rw [div_lt_iff₀ hc]

/-! ## 5. 论文关键数值结论的形式化核验 -/

/-- 【论文 §1.3、§3.2】"一次命中"的依据：P 含于以 c 为心、R_c 为半径的圆盘，真实源 G ∈ P，
故清除点 c 到源的距离 ≤ R_c；当 R_c ≤ 20 m 时一次 /clear 必命中。 -/
theorem clearing_center_within {P : Set Pt} {c G : Pt} {Rc : ℝ}
    (hsub : P ⊆ Metric.closedBall c Rc) (hG : G ∈ P) : dist c G ≤ Rc := by
  have := Metric.mem_closedBall.mp (hsub hG)
  rwa [dist_comm] at this

/-- 论文 §3.1 的覆盖半径函数 `R_cov(ρ) = max{ρ/√3, √(R_T²+ρ²-√3ρR_T)}`。 -/
def ringCov (RT ρ : ℝ) : ℝ :=
  max (ρ / Real.sqrt 3) (Real.sqrt (RT ^ 2 + ρ ^ 2 - Real.sqrt 3 * ρ * RT))

lemma sqrt3_ge : (1.73204 : ℝ) ≤ Real.sqrt 3 :=
  (Real.le_sqrt (by norm_num) (by norm_num)).mpr (by norm_num)

/-- 配方：`R_T² + ρ² - √3ρR_T = (ρ - √3R_T/2)² + R_T²/4`。 -/
lemma ring_radicand (RT ρ : ℝ) :
    RT ^ 2 + ρ ^ 2 - Real.sqrt 3 * ρ * RT
      = (ρ - Real.sqrt 3 * RT / 2) ^ 2 + RT ^ 2 / 4 := by
  nlinarith [sqrt3_sq]

/-- 【论文式 (eq:ring) 的极小值】`min_ρ R_cov(ρ) = R_T/2`，最小值在 `ρ* = √3R_T/2` 处取到。
（论文中的 `ρ* = 1558.8 m`、`R_cov = 900.0 m` 即 `R_T = 1800` 时此式之值。） -/
theorem ringCov_min (RT : ℝ) (hRT : 0 ≤ RT) :
    (∀ ρ, 0 ≤ ρ → RT / 2 ≤ ringCov RT ρ) ∧
    ringCov RT (Real.sqrt 3 * RT / 2) = RT / 2 := by
  constructor
  · intro ρ _
    rcases le_total (Real.sqrt 3 * RT / 2) ρ with h | h
    · have h1 : RT / 2 ≤ ρ / Real.sqrt 3 := by
        rw [le_div_iff₀ sqrt3_pos]
        nlinarith [sqrt3_sq, sqrt3_pos, h]
      exact le_trans h1 (le_max_left _ _)
    · have hg : RT / 2 ≤ Real.sqrt (RT ^ 2 + ρ ^ 2 - Real.sqrt 3 * ρ * RT) := by
        rw [ring_radicand]
        have h2 : (RT / 2) ^ 2 ≤ (ρ - Real.sqrt 3 * RT / 2) ^ 2 + RT ^ 2 / 4 := by
          nlinarith [sq_nonneg (ρ - Real.sqrt 3 * RT / 2)]
        have hs := Real.sqrt_le_sqrt h2
        rwa [Real.sqrt_sq_eq_abs, abs_of_nonneg (by linarith : (0 : ℝ) ≤ RT / 2)] at hs
      exact le_trans hg (le_max_right _ _)
  · have h1 : (Real.sqrt 3 * RT / 2) / Real.sqrt 3 = RT / 2 := by
      field_simp
    have h2 : RT ^ 2 + (Real.sqrt 3 * RT / 2) ^ 2 - Real.sqrt 3 * (Real.sqrt 3 * RT / 2) * RT
        = (RT / 2) ^ 2 := by
      nlinarith [sqrt3_sq]
    rw [ringCov, h1, h2, Real.sqrt_sq_eq_abs,
      abs_of_nonneg (by linarith : (0 : ℝ) ≤ RT / 2)]
    exact max_self _

/-- 【论文 §3.1】取 `ρ = 1300 m`（`R_T = 1800 m`）时判据式 (eq:cover) 成立：`R_cov ≤ 1000 m`。 -/
theorem ringCov_1300 : ringCov 1800 1300 ≤ 1000 := by
  rw [ringCov]
  apply max_le
  · rw [div_le_iff₀ sqrt3_pos]
    nlinarith [sqrt3_ge]
  · rw [Real.sqrt_le_iff]
    refine ⟨by norm_num, ?_⟩
    nlinarith [sqrt3_ge]

/-- 【论文式 (eq:ring-range)】`ρ = 1123` 与 `ρ = 1732` 两个端点处判据仍成立（区间下、上端）。 -/
theorem ringCov_range_endpoints :
    ringCov 1800 1123 ≤ 1000 ∧ ringCov 1800 1732 ≤ 1000 := by
  constructor <;> rw [ringCov] <;> apply max_le
  · rw [div_le_iff₀ sqrt3_pos]; nlinarith [sqrt3_ge]
  · rw [Real.sqrt_le_iff]; exact ⟨by norm_num, by nlinarith [sqrt3_ge]⟩
  · rw [div_le_iff₀ sqrt3_pos]; nlinarith [sqrt3_ge]
  · rw [Real.sqrt_le_iff]; exact ⟨by norm_num, by nlinarith [sqrt3_ge]⟩

/-- cos 15° 的精确值（问题四外环用 `n = 12`：`π/n = 15°`）。 -/
lemma cos_pi_div_twelve_val :
    Real.cos (Real.pi / 12) = (Real.sqrt 6 + Real.sqrt 2) / 4 := by
  have h : Real.pi / 12 = Real.pi / 3 - Real.pi / 4 := by ring
  rw [h, Real.cos_sub, Real.cos_pi_div_three, Real.sin_pi_div_three, Real.cos_pi_div_four,
    Real.sin_pi_div_four]
  have h36 : Real.sqrt 3 * Real.sqrt 2 = Real.sqrt 6 := by
    rw [← Real.sqrt_mul (by norm_num : (0 : ℝ) ≤ 3)]; norm_num
  rw [show Real.sqrt 3 / 2 * (Real.sqrt 2 / 2) = Real.sqrt 3 * Real.sqrt 2 / 4 by ring, h36]
  ring

/-- sin 15° 的精确值。 -/
lemma sin_pi_div_twelve_val :
    Real.sin (Real.pi / 12) = (Real.sqrt 6 - Real.sqrt 2) / 4 := by
  have h : Real.pi / 12 = Real.pi / 3 - Real.pi / 4 := by ring
  rw [h, Real.sin_sub, Real.sin_pi_div_three, Real.cos_pi_div_four, Real.cos_pi_div_three,
    Real.sin_pi_div_four]
  have h36 : Real.sqrt 3 * Real.sqrt 2 = Real.sqrt 6 := by
    rw [← Real.sqrt_mul (by norm_num : (0 : ℝ) ≤ 3)]; norm_num
  rw [show Real.sqrt 3 / 2 * (Real.sqrt 2 / 2) = Real.sqrt 3 * Real.sqrt 2 / 4 by ring, h36]
  ring

lemma sqrt2_bounds : (1.414 : ℝ) ≤ Real.sqrt 2 ∧ Real.sqrt 2 ≤ 1.415 := by
  constructor
  · exact (Real.le_sqrt (by norm_num) (by norm_num)).mpr (by norm_num)
  · rw [Real.sqrt_le_iff]; exact ⟨by norm_num, by norm_num⟩

lemma sqrt6_bounds : (2.449 : ℝ) ≤ Real.sqrt 6 ∧ Real.sqrt 6 ≤ 2.45 := by
  constructor
  · exact (Real.le_sqrt (by norm_num) (by norm_num)).mpr (by norm_num)
  · rw [Real.sqrt_le_iff]; exact ⟨by norm_num, by norm_num⟩

/-- 【论文表 `tab:p4-tangent`】外环 `ρ = 1900, n = 12` 满足外切条件
`ρ·cos(π/12) > R_T = 1800`；`ρ = 1950` 亦然。 -/
theorem outer_ring_tangent_ok :
    1800 < 1900 * Real.cos (Real.pi / 12) ∧ 1800 < 1950 * Real.cos (Real.pi / 12) := by
  obtain ⟨h2a, h2b⟩ := sqrt2_bounds
  obtain ⟨h6a, h6b⟩ := sqrt6_bounds
  rw [cos_pi_div_twelve_val]
  constructor <;> nlinarith

/-- 【论文式 (eq:p4-chord)】外环弦长条件：`ρ = 1900, n = 12` 合格（`2ρ sin15° ≤ 1000`），
而 `ρ = 1950` 不合格（`> 1000`），与论文表 `tab:p4-verify` 的"1900 可证、1950 不可证"一致。 -/
theorem outer_ring_chord :
    2 * 1900 * Real.sin (Real.pi / 12) ≤ 1000 ∧
    1000 < 2 * 1950 * Real.sin (Real.pi / 12) := by
  obtain ⟨h2a, h2b⟩ := sqrt2_bounds
  obtain ⟨h6a, h6b⟩ := sqrt6_bounds
  rw [sin_pi_div_twelve_val]
  constructor <;> nlinarith

end Renzheng
