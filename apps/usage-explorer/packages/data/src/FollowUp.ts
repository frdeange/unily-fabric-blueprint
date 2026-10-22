import { date, entity, role, set, text, uuid } from '@microsoft/rayfin-core';

@entity()
@role('authenticated', ['create', 'read'], {
  policy: (claims, item) => claims.sub.eq(item.owner_id),
})
@role('authenticated', 'update', {
  policy: (claims, item) => claims.sub.eq(item.owner_id),
  include: ['title', 'notes', 'status', 'priority', 'dueDate', 'updatedAt'],
})
export class FollowUp {
  @uuid() id!: string;
  @uuid() diagnosis_id!: string;
  @text({ min: 1, max: 160 }) title!: string;
  @text({ max: 2000 }) notes!: string;
  @text({ max: 200 }) owner_id!: string;
  @set('Planned', 'In progress', 'Done') status!:
    | 'Planned'
    | 'In progress'
    | 'Done';
  @set('Normal', 'High') priority!: 'Normal' | 'High';
  @text({ max: 10 }) dueDate!: string;
  @date() createdAt!: Date;
  @date() updatedAt!: Date;
}
