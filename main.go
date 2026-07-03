package main

import (
	"fmt"
	"os"

	"vdi-installer/pkg/version"
)

func main() {
	fmt.Fprintln(os.Stdout, version.FriendlyVersion())
}
