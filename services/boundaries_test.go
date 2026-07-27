package services

import "testing"

func TestFoundationVersionIsDeclared(t *testing.T) {
	if FoundationVersion == "" {
		t.Fatal("foundation version must be declared")
	}
}
