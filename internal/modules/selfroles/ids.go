package selfroles

import "fmt"

const (
	// OpenCustomID is rendered by the admin dashboard.
	OpenCustomID        = "selfroles:open"
	ToggleCustomID      = "selfroles:toggle"
	CreateCustomID      = "selfroles:create"
	GroupSelectCustomID = "selfroles:group"
	BackCustomID        = "selfroles:back"

	ToggleModePrefix = "selfroles:mode:"
	EditLimitsPrefix = "selfroles:limits:"
	DeletePrefix     = "selfroles:delete:"
	AddRolePrefix    = "selfroles:addrole:"
	RemoveRolePrefix = "selfroles:removerole:"
	DeployPrefix     = "selfroles:deploy:"
	DetailsPrefix    = "selfroles:details:"
	StylePrefix      = "selfroles:style:"
	StyleBackPrefix  = "selfroles:styleback:"
	StyleRolePrefix  = "selfroles:stylerole:"
	StyleColorPrefix = "selfroles:stylecolor:"
	RoleTogglePrefix = "selfroles:role:"
	LegacyPrefix     = "self_role:"

	CreateModalID     = "selfroles:modal:create"
	LimitsModalPrefix = "selfroles:modal:limits:"
	TitleModalPrefix  = "selfroles:modal:title:"
	DescModalPrefix   = "selfroles:modal:desc:"
	ColorModalPrefix  = "selfroles:modal:color:"

	// AdminBackCustomID is handled by the admin module.
	AdminBackCustomID = "admin:modules"
)

func groupActionID(prefix, key string) string {
	return prefix + key
}

func roleToggleID(key string, roleID int64) string {
	return fmt.Sprintf("%s%s:%d", RoleTogglePrefix, key, roleID)
}

func styleColorID(key string, roleID int64) string {
	return fmt.Sprintf("%s%s:%d", StyleColorPrefix, key, roleID)
}
