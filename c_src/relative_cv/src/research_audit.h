/* Project-specific extension; see docs/第三方代码与修改说明.md. */
#ifndef RESEARCH_AUDIT_H
#define RESEARCH_AUDIT_H
#include "rtklib.h"
double research_clock(void);
void research_spp(int role,gtime_t obs,const sol_t *sol,int ok);
void research_epoch(const rtk_t *rtk,gtime_t obs,int rc,double elapsed);
void research_ils(const rtk_t *rtk,const int *ix,int nb,const double *y,const double *Qb,const double *b,const double *cost,const double *Qab);
void research_hold(const rtk_t *rtk,const double *xa,const double *H,const double *v,int nv);
void research_final(const rtk_t *rtk,int stat,const double *xa,gtime_t obs);
void research_motion(const rtk_t *rtk,int phase);
#endif
