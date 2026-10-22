import {
  date,
  decimal,
  entity,
  int,
  role,
  text,
  uuid,
} from '@microsoft/rayfin-core';

@entity()
@role('authenticated', ['create', 'read'], {
  policy: (claims, item) => claims.sub.eq(item.owner_id),
})
@role('authenticated', 'update', {
  policy: (claims, item) => claims.sub.eq(item.owner_id),
  include: ['title', 'notes'],
})
export class Diagnosis {
  @uuid() id!: string;
  @text({ min: 1, max: 160 }) title!: string;
  @text({ max: 2000 }) notes!: string;
  @text({ max: 200 }) owner_id!: string;
  @text({ max: 200 }) tenant!: string;
  @text({ max: 7 }) period!: string;
  @text({ max: 200 }) feature!: string;
  @int() events!: number;
  @int() activeUsers!: number;
  @decimal({ optional: true }) avgDuration?: number;
  @int({ optional: true }) previousEvents?: number;
  @int({ optional: true }) previousUsers?: number;
  @date() capturedAt!: Date;
}
