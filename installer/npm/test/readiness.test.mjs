import test from 'node:test';
import assert from 'node:assert/strict';
import {softwareStatus} from '../cli.mjs';

test('software readiness is not full capability or account acceptance',()=>{
  assert.equal(softwareStatus([{id:'core',required:true,status:'verified'},{id:'services',required:false,status:'blocked'},{id:'accounts',required:false,status:'not-configured'}]),'ready-for-setup');
});
test('required missing/unknown states cannot become ready and actual failures remain failures',()=>{
  assert.equal(softwareStatus([]),'failed');
  for(const status of ['blocked','not-configured','unknown']) assert.equal(softwareStatus([{required:true,status}]),'blocked');
  assert.equal(softwareStatus([{required:true,status:'verified'},{required:false,status:'failed'}]),'failed');
});
