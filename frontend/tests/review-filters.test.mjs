import test from 'node:test';
import assert from 'node:assert/strict';
import {matchesReviewStatus} from '../src/hooks/reviewState.ts';
const row=(direction,state,review_status)=>({direction,state,review_status});
test('공제·불공제는 확정 매입만, 확인 필요는 미확정 매출도 포함한다',()=>{
  assert.equal(matchesReviewStatus(row('purchase','confirmed','analyzed'),'deductible'),true);
  assert.equal(matchesReviewStatus(row('purchase','draft','analyzed'),'deductible'),false);
  assert.equal(matchesReviewStatus(row('sales','confirmed','analyzed'),'deductible'),false);
  assert.equal(matchesReviewStatus(row('purchase','confirmed','excluded'),'nondeductible'),true);
  assert.equal(matchesReviewStatus(row('purchase','confirmed','analyzed'),'nondeductible'),false);
  assert.equal(matchesReviewStatus(row('sales','draft','not_analyzed'),'review'),true);
  assert.equal(matchesReviewStatus(row('sales','confirmed','not_analyzed'),'review'),false);
  assert.equal(matchesReviewStatus(row('purchase','confirmed','caution'),'review'),true);
});
