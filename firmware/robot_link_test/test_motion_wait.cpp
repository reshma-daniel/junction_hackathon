#include <assert.h>
#include <stdint.h>
#include "motion_wait.cpp"
static void advance(MotionDrive& d,uint32_t from,uint32_t to,float rssi,bool fresh=true) {
 for(uint32_t t=from;t<=to;t+=20){d.ping(t);d.tick(t,fresh,rssi);}
}
static MotionDrive active() {
 MotionDrive d;d.receive(false,0);advance(d,0,10000,-75);
 assert(d.started && d.phase==MotionDrive::APPROACH && d.speed==255);
 assert(d.initialRssiValid && d.initialRssi==-75);return d;
}
int main() {
 MotionDrive session;
 session.beginSession();session.tick(0,false,0);assert(!session.initialRssiValid);
 session.tick(1,true,-92);assert(session.initialRssi==-92 && session.speed==0);
 session.receive(false,10);advance(session,10,10010,-80);
 assert(session.initialRssi==-92 && session.started);
 session.receive(true,10020);session.tick(10020,true,-80);
 assert(session.leadInitialRssi==-92 && session.phase==MotionDrive::LEAD);
 session.ping(11000);session.tick(11000,true,-93.54f);assert(session.phase==MotionDrive::LEAD);
 session.ping(11020);session.tick(11020,true,-93.56f);assert(session.returning && session.target==255);
 advance(session,11040,12000,-85);assert(session.returning && session.speed==255);
 session.ping(12020);session.tick(12020,true,-80);assert(session.phase==MotionDrive::LEAD && !session.returning);
 advance(session,12040,13000,-80);assert(session.speed==-255 && session.initialRssi==-92);
 session.ping(13020);session.tick(13020,true,-94);assert(session.returning);
 advance(session,13040,14000,-80);assert(session.phase==MotionDrive::LEAD && session.initialRssi==-92);
 session.beginSession();assert(session.speed==0 && !session.initialRssiValid);
 session.tick(10040,true,-88);assert(session.initialRssi==-88);

 MotionDrive d;d.receive(true,0);advance(d,0,2000,-75);assert(d.phase==MotionDrive::IDLE);
 d.stop();d.receive(false,0);advance(d,0,4980,-75);d.receive(false,5000);
 advance(d,5000,9980,-75);assert(d.phase==MotionDrive::STILL_WAIT && !d.speed);
 advance(d,10000,10000,-75);assert(d.started && d.speed==255);
 advance(d,10020,16000,-65);assert(d.speed==255); // No RSSI speed changes.
 d=active();d.receive(true,11020);assert(d.target==-255 && d.speed==0);
 d.tick(11020,true,-75);advance(d,11040,11200,-75);assert(d.speed==0);
 d.tick(11220,true,-75);assert(d.speed==-255);
 d.receive(false,11240);d.tick(11240,true,-75);
 assert(d.phase==MotionDrive::LEAD && d.speed==-255); // Still does not return.
 d.receive(true,11260);d.tick(11260,true,-75);
 assert(d.leadInitialRssi==-75 && d.speed==-255); // Do not reset baseline.
 d.tick(12020,true,-76.54f);assert(d.phase==MotionDrive::LEAD);
 d.tick(12040,true,-82.0f);assert(d.phase==MotionDrive::APPROACH && d.target==255 && !d.speed);
 d.receive(true,12060);assert(d.phase==MotionDrive::APPROACH);
 advance(d,12060,13000,-82);assert(d.speed==255);
 d.receive(false,13020);d.tick(13020,true,-82);assert(d.speed==255);
 d.receive(true,13040);d.tick(13040,true,-82);
 assert(d.returning && d.target==255); // IMU cannot interrupt a return.
 d.tick(13060,true,-80.01f);assert(d.returning);
 d.tick(13080,true,-80.0f);assert(!d.returning && d.phase==MotionDrive::LEAD && d.speed==0);
 advance(d,13100,14000,-76);
 assert(d.phase==MotionDrive::LEAD && d.speed==-255);
 d.tick(14020,false,0);assert(!d.speed && !d.target);
 advance(d,14040,15000,-76);assert(d.speed==-255);
 d.tick(18000,true,-76);assert(!d.armed && !d.started && !d.speed);
 d.ping(18001);assert(!d.armed);
 d.receive(false,20000);d.receive(true,25000);advance(d,25000,31000,-70);
 assert(d.phase==MotionDrive::IDLE && !d.started);
 d.stop();d.receive(false,UINT32_MAX-5000);
 d.ping(4998);d.tick(4998,true,-70);assert(!d.started);
 d.ping(4999);d.tick(4999,true,-70);assert(d.started && d.speed==255);
 d.stop();assert(d.lastMoving==-1 && !d.started && !d.initialRssiValid);
}
