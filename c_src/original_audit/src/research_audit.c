/* Project-specific extension; see docs/第三方代码与修改说明.md. */
/* Read-only research instrumentation; native matrices are column-major.
 * JSON matrices explicitly exported as row arrays; H is nx x nv. */
#include "research_audit.h"
#include <time.h>
static FILE *openlog(void){const char *p=getenv("RTK_RESEARCH_AUDIT");return p?fopen(p,"a"):NULL;}
static double day(gtime_t t){return fmod(time2gpst(t,NULL),86400.0);}
static void tm(FILE*f,const char*k,gtime_t t){fprintf(f,"\"%s\":[%lld,%.17g]",k,(long long)t.time,t.sec);}
static void jmat(FILE*f,const char*k,const double*x,int n,int m){int i,j;fprintf(f,"\"%s\":[",k);for(i=0;i<n;i++){fprintf(f,"%s[",i?",":"");for(j=0;j<m;j++)fprintf(f,"%s%.17g",j?",":"",x[i+j*n]);fprintf(f,"]");}fprintf(f,"]");}
double research_clock(void){struct timespec ts;clock_gettime(CLOCK_MONOTONIC,&ts);return ts.tv_sec+ts.tv_nsec*1e-9;}
void research_spp(int role,gtime_t obs,const sol_t*s,int ok){FILE*f=openlog();if(!f)return;fprintf(f,"{\"event\":\"SPP\",\"role\":%d,\"tick\":%.0f,\"ok\":%d,",role,day(obs)*1e7,ok);tm(f,"time",s->time);fprintf(f,",");jmat(f,"rr",s->rr,6,1);fprintf(f,"}\n");fclose(f);}
void research_epoch(const rtk_t*r,gtime_t obs,int rc,double elapsed){FILE*f=openlog();if(!f)return;fprintf(f,"{\"event\":\"EPOCH\",\"tick\":%.0f,\"rc\":%d,\"stat\":%d,\"elapsed_s\":%.17g,\"legacy_dt\":%.17g,\"age\":%.17g,",day(obs)*1e7,rc,r->sol.stat,elapsed,r->tt,r->sol.age);tm(f,"time",r->sol.time);fprintf(f,",");jmat(f,"rr",r->sol.rr,6,1);fprintf(f,",");jmat(f,"rb",r->rb,6,1);
#ifdef RTK_REL_RESEARCH
 fprintf(f,",\"rel_error\":%d,\"rel_initialized\":%d,\"rel_action\":%d,\"state_dt\":%.17g,",r->rel_error,r->rel_initialized,r->rel_action,r->rel_dt);tm(f,"state_time",r->rel_time);fprintf(f,",");jmat(f,"state_anchor",r->rel_anchor,3,1);
#else
 fprintf(f,",\"rel_error\":0,\"rel_initialized\":0,\"rel_action\":0,\"state_dt\":0,\"state_time\":[0,0],\"state_anchor\":[[0],[0],[0]]");
#endif
 fprintf(f,"}\n");fclose(f);}
void research_ils(const rtk_t*r,const int*ix,int nb,const double*y,const double*Qb,const double*b,const double*s){FILE*f=openlog();int i;if(!f)return;fprintf(f,"{\"event\":\"ILS\",\"time_day\":%.17g,\"nfix\":%d,\"costs\":[%.17g,%.17g],\"pairs\":[",day(r->sol.time),r->nfix,s[0],s[1]);for(i=0;i<nb;i++)fprintf(f,"%s[%d,%d]",i?",":"",ix[i*2],ix[i*2+1]);fprintf(f,"],");jmat(f,"a",y,nb,1);fprintf(f,",");jmat(f,"Qb",Qb,nb,nb);fprintf(f,",");jmat(f,"candidates",b,nb,2);fprintf(f,"}\n");fclose(f);}
void research_hold(const rtk_t*r,const double*xa,const double*H,const double*v,int nv){FILE*f=openlog();int i,j,a,b;if(!f)return;fprintf(f,"{\"event\":\"HOLD\",\"time_day\":%.17g,\"nfix\":%d,\"edges\":[",day(r->sol.time),r->nfix);for(j=0;j<nv;j++){a=b=-1;for(i=0;i<r->nx;i++){if(H[i+j*r->nx]==1.)a=i;if(H[i+j*r->nx]==-1.)b=i;}fprintf(f,"%s{\"ref\":%d,\"sat\":%d,\"freq\":%d,\"N\":%.17g,\"v\":%.17g}",j?",":"",(a-r->na)%MAXSAT+1,(b-r->na)%MAXSAT+1,(a-r->na)/MAXSAT,xa[a]-xa[b],v[j]);}fprintf(f,"]}\n");fclose(f);}
void research_final(const rtk_t*r,int stat,const double*xa,gtime_t obs){FILE*f=openlog();int nf=r->opt.ionoopt==IONOOPT_IFLC?1:r->opt.nf,i,j,k,n=r->na,*ids,s,fr,ref,root,first=1;double*x,*P; if(!f)return;ids=imat(r->nx,1);for(i=0;i<n;i++)ids[i]=i;
 fprintf(f,"{\"event\":\"REL\",\"tick\":%.0f,\"stat\":%d,\"ratio\":%.17g,\"nfix\":%d,\"na\":%d,\"nx\":%d,\"nodes\":[",day(obs)*1e7,stat,(double)r->sol.ratio,r->nfix,r->na,r->nx);
 for(fr=0;fr<nf;fr++)for(s=1;s<=MAXSAT;s++){i=r->na+MAXSAT*fr+s-1;if(i>=r->nx||r->x[i]==0.)continue;ids[n++]=i;fprintf(f,"%s{\"index\":%d,\"freq\":%d,\"sat\":%d,\"lock\":%d,\"outc\":%u,\"slip\":%u,\"half\":%u,\"fix\":%u}",first?"":",",i,fr,s,r->ssat[s-1].lock[fr],r->ssat[s-1].outc[fr],r->ssat[s-1].slip[fr],r->ssat[s-1].half[fr],r->ssat[s-1].fix[fr]);first=0;}
 fprintf(f,"],\"accepted_edges\":[");first=1;if(stat==SOLQ_FIX)for(fr=0;fr<nf;fr++){ref=root=0;for(s=1;s<=MAXSAT;s++){if(r->ssat[s-1].sys!=SYS_GPS||(r->ssat[s-1].fix[fr]!=2&&r->ssat[s-1].fix[fr]!=3))continue;i=r->na+MAXSAT*fr+s-1;if(!ref){ref=s;root=i;continue;}fprintf(f,"%s{\"freq\":%d,\"ref\":%d,\"sat\":%d,\"N\":%.17g}",first?"":",",fr,ref,s,xa[root]-xa[i]);first=0;}}
 fprintf(f,"],");x=mat(n,1);P=mat(n,n);for(i=0;i<n;i++){x[i]=r->x[ids[i]];for(j=0;j<n;j++)P[i+j*n]=r->P[ids[i]+ids[j]*r->nx];}jmat(f,"x",x,n,1);fprintf(f,",");jmat(f,"P",P,n,n);fprintf(f,",");jmat(f,"fixed_x",r->xa,r->na,1);fprintf(f,",");jmat(f,"fixed_P",r->Pa,r->na,r->na);fprintf(f,",");jmat(f,"rb",r->rb,6,1);fprintf(f,",");jmat(f,"rr",r->sol.rr,6,1);fprintf(f,"}\n");free(x);free(P);free(ids);fclose(f);}
void research_motion(const rtk_t*r,int phase){FILE*f=openlog();int i;if(!f)return;fprintf(f,"{\"event\":\"MOTION\",\"phase\":%d,\"time_day\":%.17g,\"legacy_dt\":%.17g,\"physical_active\":[",phase,day(r->sol.time),r->tt);for(i=0;i<(r->opt.dynamics?9:3);i++)fprintf(f,"%s%d",i?",":"",r->x[i]!=0.&&r->P[i+i*r->nx]>0.);fprintf(f,"],");jmat(f,"physical_x",r->x,r->opt.dynamics?9:3,1);fprintf(f,"}\n");fclose(f);}
