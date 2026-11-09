/* Project-specific extension; see docs/第三方代码与修改说明.md. */
#ifndef RELMOTION_H
#define RELMOTION_H
#include "rtklib.h"
int relcv_options(const prcopt_t*,char*,size_t);
int relcv_predict(double*,double*,int,double,const double*,double);
int relcv_accept_input(rtk_t*,gtime_t);
int relcv_state(rtk_t*);
int research_prior_valid(const double*,const double*,int,int);
int relcv_valid(const double*,const double*,int);
int filter_active_prefix(double*,double*,const double*,const double*,const double*,int,int,int);
#endif
