package system

import "container/list"

// Caller owns synchronization. Capacity bounds all key-indexed state.
type item[T any] struct {
	key   string
	value T
}
type lru[T any] struct {
	capacity int
	order    *list.List
	items    map[string]*list.Element
}

func newLRU[T any](capacity int) *lru[T] {
	return &lru[T]{capacity: capacity, order: list.New(), items: make(map[string]*list.Element)}
}
func (l *lru[T]) get(k string) (T, bool) {
	if e, ok := l.items[k]; ok {
		l.order.MoveToFront(e)
		return e.Value.(item[T]).value, true
	}
	var zero T
	return zero, false
}
func (l *lru[T]) put(k string, v T) bool {
	if e, ok := l.items[k]; ok {
		e.Value = item[T]{k, v}
		l.order.MoveToFront(e)
		return false
	}
	l.items[k] = l.order.PushFront(item[T]{k, v})
	if len(l.items) > l.capacity {
		l.remove(l.order.Back().Value.(item[T]).key)
		return true
	}
	return false
}
func (l *lru[T]) remove(k string) {
	if e, ok := l.items[k]; ok {
		l.order.Remove(e)
		delete(l.items, k)
	}
}
