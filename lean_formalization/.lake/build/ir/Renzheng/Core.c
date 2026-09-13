// Lean compiler output
// Module: Renzheng.Core
// Imports: public import Init public meta import Init public import Mathlib
#include <lean/lean.h>
#if defined(__clang__)
#pragma clang diagnostic ignored "-Wunused-parameter"
#pragma clang diagnostic ignored "-Wunused-label"
#elif defined(__GNUC__) && !defined(__CLANG__)
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-label"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"
#endif
#ifdef __cplusplus
extern "C" {
#endif
lean_object* lp_mathlib_Nat_cast___at___00Nat_cast___at___00Nat_cast___at___00Nat_cast___at___00__private_Mathlib_NumberTheory_ModularForms_EisensteinSeries_E2_Transform_0__EisensteinSeries_00_u03b4_spec__0_spec__0_spec__2_spec__3(lean_object*);
lean_object* lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_4214226450____hygCtx___hyg_8_(lean_object*, lean_object*, lean_object*);
lean_object* lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_2451848184____hygCtx___hyg_8_(lean_object*, lean_object*);
lean_object* lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_1138242547____hygCtx___hyg_8_(lean_object*, lean_object*, lean_object*);
extern lean_object* lp_mathlib_Real_definition_00___x40_Mathlib_Data_Real_Basic_1850581184____hygCtx___hyg_8_;
extern lean_object* lp_mathlib_Real_definition_00___x40_Mathlib_Data_Real_Basic_1279875089____hygCtx___hyg_8_;
lean_object* lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_3793047190____hygCtx___hyg_8_(lean_object*, lean_object*, lean_object*);
lean_object* lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_1934218611____hygCtx___hyg_8_(lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_renzheng_Renzheng_dot(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_renzheng_Renzheng_cross(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_renzheng_Renzheng_dotL___lam__0(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_renzheng_Renzheng_dotL(lean_object*);
LEAN_EXPORT lean_object* lp_renzheng_Renzheng_down(lean_object*);
static lean_once_cell_t lp_renzheng_Renzheng_refineStep___closed__0_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_renzheng_Renzheng_refineStep___closed__0;
static lean_once_cell_t lp_renzheng_Renzheng_refineStep___closed__1_once = LEAN_ONCE_CELL_INITIALIZER;
static lean_object* lp_renzheng_Renzheng_refineStep___closed__1;
LEAN_EXPORT lean_object* lp_renzheng_Renzheng_refineStep(lean_object*);
LEAN_EXPORT lean_object* lp_renzheng_Renzheng_dot(lean_object* v_z_1_, lean_object* v_w_2_){
_start:
{
lean_object* v_re_3_; lean_object* v_im_4_; lean_object* v_re_5_; lean_object* v_im_6_; lean_object* v___f_7_; lean_object* v___f_8_; lean_object* v___f_9_; 
v_re_3_ = lean_ctor_get(v_z_1_, 0);
lean_inc(v_re_3_);
v_im_4_ = lean_ctor_get(v_z_1_, 1);
lean_inc(v_im_4_);
lean_dec_ref(v_z_1_);
v_re_5_ = lean_ctor_get(v_w_2_, 0);
lean_inc(v_re_5_);
v_im_6_ = lean_ctor_get(v_w_2_, 1);
lean_inc(v_im_6_);
lean_dec_ref(v_w_2_);
v___f_7_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_4214226450____hygCtx___hyg_8_), 3, 2);
lean_closure_set(v___f_7_, 0, v_re_3_);
lean_closure_set(v___f_7_, 1, v_re_5_);
v___f_8_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_4214226450____hygCtx___hyg_8_), 3, 2);
lean_closure_set(v___f_8_, 0, v_im_4_);
lean_closure_set(v___f_8_, 1, v_im_6_);
v___f_9_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_1138242547____hygCtx___hyg_8_), 3, 2);
lean_closure_set(v___f_9_, 0, v___f_7_);
lean_closure_set(v___f_9_, 1, v___f_8_);
return v___f_9_;
}
}
LEAN_EXPORT lean_object* lp_renzheng_Renzheng_cross(lean_object* v_z_10_, lean_object* v_w_11_){
_start:
{
lean_object* v_re_12_; lean_object* v_im_13_; lean_object* v_re_14_; lean_object* v_im_15_; lean_object* v___f_16_; lean_object* v___f_17_; lean_object* v___f_18_; lean_object* v___f_19_; 
v_re_12_ = lean_ctor_get(v_z_10_, 0);
lean_inc(v_re_12_);
v_im_13_ = lean_ctor_get(v_z_10_, 1);
lean_inc(v_im_13_);
lean_dec_ref(v_z_10_);
v_re_14_ = lean_ctor_get(v_w_11_, 0);
lean_inc(v_re_14_);
v_im_15_ = lean_ctor_get(v_w_11_, 1);
lean_inc(v_im_15_);
lean_dec_ref(v_w_11_);
v___f_16_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_4214226450____hygCtx___hyg_8_), 3, 2);
lean_closure_set(v___f_16_, 0, v_re_12_);
lean_closure_set(v___f_16_, 1, v_im_15_);
v___f_17_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_4214226450____hygCtx___hyg_8_), 3, 2);
lean_closure_set(v___f_17_, 0, v_im_13_);
lean_closure_set(v___f_17_, 1, v_re_14_);
v___f_18_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_2451848184____hygCtx___hyg_8_), 2, 1);
lean_closure_set(v___f_18_, 0, v___f_17_);
v___f_19_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_1138242547____hygCtx___hyg_8_), 3, 2);
lean_closure_set(v___f_19_, 0, v___f_16_);
lean_closure_set(v___f_19_, 1, v___f_18_);
return v___f_19_;
}
}
LEAN_EXPORT lean_object* lp_renzheng_Renzheng_dotL___lam__0(lean_object* v_n_20_, lean_object* v_z_21_){
_start:
{
lean_object* v___x_22_; 
v___x_22_ = lp_renzheng_Renzheng_dot(v_z_21_, v_n_20_);
return v___x_22_;
}
}
LEAN_EXPORT lean_object* lp_renzheng_Renzheng_dotL(lean_object* v_n_23_){
_start:
{
lean_object* v___f_24_; 
v___f_24_ = lean_alloc_closure((void*)(lp_renzheng_Renzheng_dotL___lam__0), 2, 1);
lean_closure_set(v___f_24_, 0, v_n_23_);
return v___f_24_;
}
}
LEAN_EXPORT lean_object* lp_renzheng_Renzheng_down(lean_object* v_t_25_){
_start:
{
lean_object* v___x_26_; lean_object* v___f_27_; lean_object* v___x_28_; 
v___x_26_ = lp_mathlib_Real_definition_00___x40_Mathlib_Data_Real_Basic_1850581184____hygCtx___hyg_8_;
v___f_27_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_2451848184____hygCtx___hyg_8_), 2, 1);
lean_closure_set(v___f_27_, 0, v_t_25_);
v___x_28_ = lean_alloc_ctor(0, 2, 0);
lean_ctor_set(v___x_28_, 0, v___x_26_);
lean_ctor_set(v___x_28_, 1, v___f_27_);
return v___x_28_;
}
}
static lean_object* _init_lp_renzheng_Renzheng_refineStep___closed__0(void){
_start:
{
lean_object* v___x_29_; lean_object* v___x_30_; 
v___x_29_ = lean_unsigned_to_nat(950u);
v___x_30_ = lp_mathlib_Nat_cast___at___00Nat_cast___at___00Nat_cast___at___00Nat_cast___at___00__private_Mathlib_NumberTheory_ModularForms_EisensteinSeries_E2_Transform_0__EisensteinSeries_00_u03b4_spec__0_spec__0_spec__2_spec__3(v___x_29_);
return v___x_30_;
}
}
static lean_object* _init_lp_renzheng_Renzheng_refineStep___closed__1(void){
_start:
{
lean_object* v___x_31_; lean_object* v___x_32_; 
v___x_31_ = lean_unsigned_to_nat(100u);
v___x_32_ = lp_mathlib_Nat_cast___at___00Nat_cast___at___00Nat_cast___at___00Nat_cast___at___00__private_Mathlib_NumberTheory_ModularForms_EisensteinSeries_E2_Transform_0__EisensteinSeries_00_u03b4_spec__0_spec__0_spec__2_spec__3(v___x_31_);
return v___x_32_;
}
}
LEAN_EXPORT lean_object* lp_renzheng_Renzheng_refineStep(lean_object* v_Rc_33_){
_start:
{
lean_object* v___x_34_; lean_object* v___f_35_; lean_object* v___x_36_; lean_object* v___f_37_; lean_object* v___f_38_; lean_object* v___x_39_; lean_object* v___f_40_; lean_object* v___f_41_; 
v___x_34_ = lp_mathlib_Real_definition_00___x40_Mathlib_Data_Real_Basic_1279875089____hygCtx___hyg_8_;
lean_inc(v_Rc_33_);
v___f_35_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_3793047190____hygCtx___hyg_8_), 3, 2);
lean_closure_set(v___f_35_, 0, v_Rc_33_);
lean_closure_set(v___f_35_, 1, v___x_34_);
v___x_36_ = lean_obj_once(&lp_renzheng_Renzheng_refineStep___closed__0, &lp_renzheng_Renzheng_refineStep___closed__0_once, _init_lp_renzheng_Renzheng_refineStep___closed__0);
v___f_37_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_2451848184____hygCtx___hyg_8_), 2, 1);
lean_closure_set(v___f_37_, 0, v_Rc_33_);
v___f_38_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_1138242547____hygCtx___hyg_8_), 3, 2);
lean_closure_set(v___f_38_, 0, v___x_36_);
lean_closure_set(v___f_38_, 1, v___f_37_);
v___x_39_ = lean_obj_once(&lp_renzheng_Renzheng_refineStep___closed__1, &lp_renzheng_Renzheng_refineStep___closed__1_once, _init_lp_renzheng_Renzheng_refineStep___closed__1);
v___f_40_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_3793047190____hygCtx___hyg_8_), 3, 2);
lean_closure_set(v___f_40_, 0, v___f_38_);
lean_closure_set(v___f_40_, 1, v___x_39_);
v___f_41_ = lean_alloc_closure((void*)(lp_mathlib_Real_definition___lam__0_00___x40_Mathlib_Data_Real_Basic_1934218611____hygCtx___hyg_8_), 3, 2);
lean_closure_set(v___f_41_, 0, v___f_35_);
lean_closure_set(v___f_41_, 1, v___f_40_);
return v___f_41_;
}
}
lean_object* initialize_Init(uint8_t builtin);
lean_object* initialize_Init(uint8_t builtin);
lean_object* initialize_mathlib_Mathlib(uint8_t builtin);
static bool _G_initialized = false;
LEAN_EXPORT lean_object* initialize_renzheng_Renzheng_Core(uint8_t builtin) {
lean_object * res;
if (_G_initialized) return lean_io_result_mk_ok(lean_box(0));
_G_initialized = true;
res = initialize_Init(builtin);
if (lean_io_result_is_error(res)) return res;
lean_dec_ref(res);
res = initialize_Init(builtin);
if (lean_io_result_is_error(res)) return res;
lean_dec_ref(res);
res = initialize_mathlib_Mathlib(builtin);
if (lean_io_result_is_error(res)) return res;
lean_dec_ref(res);
return lean_io_result_mk_ok(lean_box(0));
}
#ifdef __cplusplus
}
#endif
