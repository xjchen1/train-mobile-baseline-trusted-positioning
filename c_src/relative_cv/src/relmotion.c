/* Project-specific extension; see docs/第三方代码与修改说明.md. */
/* Conditional relative CV in native ECEF position coordinates.
 * x[0:3] = current base SPP anchor + baseline; x[3:6] = relative velocity.
 * Preserve the native phase-bias representation and native measurement kernel. */
#include "relmotion.h"
int relcv_options(const prcopt_t*o,char*msg,size_t n){
 if(!o->relmotion)return 0;
 if(o->relmotion!=1||o->mode!=PMODE_MOVEB||o->dynamics||o->soltype||o->nf!=2||o->navsys!=SYS_GPS||o->sateph!=EPHOPT_BRDC||o->ionoopt!=IONOOPT_BRDC||o->tropopt!=TROPOPT_SAAS||o->intpref||o->baseline[0]!=0.||o->baseline[1]!=0.||!isfinite(o->relq)||o->relq<0.||!isfinite(o->relv0)||o->relv0<=0.){
  snprintf(msg,n,"relative CV requires forward GPS L1/L2 movingbase, dynamics/intpref/baseline off, BRDC/SAAS, finite q>=0 and v0>0");return -1;
 }return 0;
}
int relcv_predict(double*x,double*P,int n,double dt,const double*da,double q){
 double old[36],dt2=dt*dt,dt3=dt2*dt;int i,j;
 if(n<6||!isfinite(dt)||dt<0.||!isfinite(q)||q<0.)return -1;
 for(i=0;i<3;i++)if(!isfinite(da[i]))return -1;
 for(i=0;i<n;i++)if(!isfinite(x[i]))return -1;
 for(i=0;i<n*n;i++)if(!isfinite(P[i]))return -1;
 for(j=0;j<6;j++)for(i=0;i<6;i++)old[i+j*6]=P[i+j*n];
 /* Sparse evaluation of FPF': all cross-covariances are retained. */
 for(j=6;j<n;j++)for(i=0;i<3;i++){
  P[i+j*n]+=dt*P[i+3+j*n];
  P[j+i*n]+=dt*P[j+(i+3)*n];
 }
 for(j=0;j<3;j++)for(i=0;i<3;i++){
  P[i+j*n]=old[i+j*6]+dt*(old[i+(j+3)*6]+old[i+3+j*6])+dt2*old[i+3+(j+3)*6]+(i==j?q*dt3/3.:0.);
  P[i+(j+3)*n]=old[i+(j+3)*6]+dt*old[i+3+(j+3)*6]+(i==j?q*dt2/2.:0.);
  P[i+3+j*n]=old[i+3+j*6]+dt*old[i+3+(j+3)*6]+(i==j?q*dt2/2.:0.);
  P[i+3+(j+3)*n]=old[i+3+(j+3)*6]+(i==j?q*dt:0.);
 }
 for(i=0;i<3;i++)x[i]+=da[i]+dt*x[i+3];
 for(i=0;i<n;i++)if(!isfinite(x[i]))return -1;
 for(i=0;i<n*n;i++)if(!isfinite(P[i]))return -1;
 return 0;
}
int relcv_accept_input(rtk_t*r,gtime_t t){
 double dt;r->rel_action=0;r->rel_dt=0.;
 if(r->rel_error)return -1;
 if(r->rel_have_input){
  dt=timediff(t,r->rel_input_time);
  if(dt==0.){r->rel_action=4;return 0;}
  if(!isfinite(dt)||dt<0.){r->rel_error=-2;return -1;}
 }
 r->rel_input_time=t;r->rel_have_input=1;return 1;
}
static void rel_setstate(rtk_t*r,int i,double mean,double var){int j;for(j=0;j<r->nx;j++)r->P[i+j*r->nx]=r->P[j+i*r->nx]=0.;r->P[i+i*r->nx]=var;r->x[i]=mean;}
static void anchor(rtk_t*r){int i;r->rel_time=r->sol.time;for(i=0;i<3;i++)r->rel_anchor[i]=r->rb[i];r->rel_initialized=1;}
int relcv_state(rtk_t*r){
 double dt=0.,da[3],var=0.;int i,reset=0;
 if(r->rel_error)return -1;
 for(i=0;i<3;i++)if(!isfinite(r->rb[i])||!isfinite(r->sol.rr[i])){r->rel_error=-3;return -1;}
 if(!isfinite(r->sol.time.sec)||r->sol.time.time==0||r->nx<6){r->rel_error=-3;return -1;}
 for(i=0;i<r->nx*r->nx;i++)if(!isfinite(r->P[i])){r->rel_error=-4;return -1;}
 if(r->rel_initialized&&!research_prior_valid(r->x,r->P,r->nx,6)){r->rel_error=-4;return -1;}
 if(r->rel_initialized){
  dt=timediff(r->sol.time,r->rel_time);r->rel_dt=dt;
  if(!isfinite(dt)||dt<=0.){r->rel_error=-5;return -1;}
  for(i=0;i<3;i++){if(r->P[i+i*r->nx]<0.){r->rel_error=-4;return -1;}var+=r->P[i+i*r->nx]/3.;}
  reset=var>900.;
 }
 if(!r->rel_initialized||reset){
  for(i=0;i<3;i++)rel_setstate(r,i,r->sol.rr[i],900.);
  for(i=3;i<6;i++)rel_setstate(r,i,0.,r->opt.relv0*r->opt.relv0);
  r->rel_action=reset?3:1;anchor(r);return 0;
 }
 for(i=0;i<3;i++)da[i]=r->rb[i]-r->rel_anchor[i];
 if(relcv_predict(r->x,r->P,r->nx,dt,da,r->opt.relq)){r->rel_error=-6;return -1;}
 r->rel_action=2;anchor(r);return 0;
}

int relcv_valid(const double*x,const double*P,int n){int i;for(i=0;i<n;i++)if(!isfinite(x[i])||!isfinite(P[i+i*n])||P[i+i*n]<-1e-10*(1.+fabs(P[i+i*n])))return 0;for(i=0;i<n*n;i++)if(!isfinite(P[i]))return 0;return 1;}
