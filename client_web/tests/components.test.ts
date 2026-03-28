import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import TaskList from '../src/components/TaskList.svelte';
import TaskCard from '../src/components/TaskCard.svelte';
import ViewToggle from '../src/components/ViewToggle.svelte';
import type { Task } from '../src/lib/api';

const mockTask: Task = {
  id: 1,
  title: 'Fix the login bug',
  assignee_id: 2,
  assignee_name: 'Alice',
  description: 'The login form breaks on mobile',
  importance: 85,
  estimated_effort: 3,
  created_time: 1700000000,
  status: 'NEW',
  tags: ['bug', 'urgent'],
  blockers: [],
};

const mockTask2: Task = {
  id: 2,
  title: 'Add dark mode',
  assignee_id: null,
  assignee_name: null,
  description: '',
  importance: 40,
  estimated_effort: 5,
  created_time: 1700001000,
  status: 'STARTED',
  tags: ['feature'],
  blockers: [1],
};

describe('TaskList', () => {
  it('renders table rows for each task', () => {
    const onselect = vi.fn();
    render(TaskList, { props: { tasks: [mockTask, mockTask2], onselect } });

    expect(screen.getByText('Fix the login bug')).toBeTruthy();
    expect(screen.getByText('Add dark mode')).toBeTruthy();
    expect(screen.getByText('#1')).toBeTruthy();
    expect(screen.getByText('#2')).toBeTruthy();
  });

  it('shows status badges', () => {
    render(TaskList, { props: { tasks: [mockTask], onselect: vi.fn() } });
    expect(screen.getByText('NEW')).toBeTruthy();
  });

  it('shows importance values', () => {
    render(TaskList, { props: { tasks: [mockTask], onselect: vi.fn() } });
    expect(screen.getByText('85')).toBeTruthy();
  });

  it('shows assignee name', () => {
    render(TaskList, { props: { tasks: [mockTask], onselect: vi.fn() } });
    expect(screen.getByText('Alice')).toBeTruthy();
  });

  it('shows tags', () => {
    render(TaskList, { props: { tasks: [mockTask], onselect: vi.fn() } });
    expect(screen.getByText('bug')).toBeTruthy();
    expect(screen.getByText('urgent')).toBeTruthy();
  });

  it('shows empty message when no tasks', () => {
    render(TaskList, { props: { tasks: [], onselect: vi.fn() } });
    expect(screen.getByText('No tasks found.')).toBeTruthy();
  });

  it('calls onselect when row is clicked', async () => {
    const onselect = vi.fn();
    render(TaskList, { props: { tasks: [mockTask], onselect } });

    await fireEvent.click(screen.getByText('Fix the login bug'));
    expect(onselect).toHaveBeenCalledWith(mockTask);
  });
});

describe('TaskCard', () => {
  it('renders task title', () => {
    render(TaskCard, { props: { task: mockTask, onclick: vi.fn() } });
    expect(screen.getByText('Fix the login bug')).toBeTruthy();
  });

  it('renders status badge', () => {
    render(TaskCard, { props: { task: mockTask, onclick: vi.fn() } });
    expect(screen.getByText('NEW')).toBeTruthy();
  });

  it('renders importance', () => {
    render(TaskCard, { props: { task: mockTask, onclick: vi.fn() } });
    expect(screen.getByText('85')).toBeTruthy();
  });

  it('renders tags as chips', () => {
    render(TaskCard, { props: { task: mockTask, onclick: vi.fn() } });
    expect(screen.getByText('bug')).toBeTruthy();
    expect(screen.getByText('urgent')).toBeTruthy();
  });

  it('renders assignee name', () => {
    render(TaskCard, { props: { task: mockTask, onclick: vi.fn() } });
    expect(screen.getByText('Alice')).toBeTruthy();
  });

  it('calls onclick when clicked', async () => {
    const onclick = vi.fn();
    render(TaskCard, { props: { task: mockTask, onclick } });

    await fireEvent.click(screen.getByText('Fix the login bug'));
    expect(onclick).toHaveBeenCalledWith(mockTask);
  });
});

describe('ViewToggle', () => {
  it('renders list and card buttons', () => {
    render(ViewToggle, { props: { view: 'list', onchange: vi.fn() } });
    expect(screen.getByLabelText('List view')).toBeTruthy();
    expect(screen.getByLabelText('Card view')).toBeTruthy();
  });

  it('calls onchange with "card" when card button clicked', async () => {
    const onchange = vi.fn();
    render(ViewToggle, { props: { view: 'list', onchange } });

    await fireEvent.click(screen.getByLabelText('Card view'));
    expect(onchange).toHaveBeenCalledWith('card');
  });

  it('calls onchange with "list" when list button clicked', async () => {
    const onchange = vi.fn();
    render(ViewToggle, { props: { view: 'card', onchange } });

    await fireEvent.click(screen.getByLabelText('List view'));
    expect(onchange).toHaveBeenCalledWith('list');
  });
});
