local W = WhaleWire
local frame = CreateFrame('Frame', 'WhaleBridgeFrame', UIParent)
frame:SetSize(W.columns * W.cell, W.rows * W.cell)
frame:SetPoint('TOPLEFT', UIParent, 'TOPLEFT', 8, -8)
frame:SetFrameStrata('TOOLTIP')
frame:EnableMouse(false)
local textures, sequence, enabled = {}, 0, true
for i = 1, W.columns * W.rows do
    local texture = frame:CreateTexture(nil, 'OVERLAY')
    texture:SetSize(W.cell, W.cell)
    texture:SetPoint('TOPLEFT', frame, 'TOPLEFT', (i - 1) % W.columns * W.cell, -math.floor((i - 1) / W.columns) * W.cell)
    textures[i] = texture
end

local function public(v)
    return not issecretvalue(v) and not (type(v) == 'table' and issecrettable(v))
end
local function number(v)
    if public(v) and type(v) == 'number' then return v end
end
local function text(v)
    if public(v) and type(v) == 'string' then return v end
end

local function snapshot()
    local state = {version = 1, sampledAt = time(), inCombat = InCombatLockdown() and true or false}
    if state.inCombat then return state end
    state.build = select(2, GetBuildInfo())
    state.zone, state.subzone = text(GetZoneText()), text(GetSubZoneText())
    state.level = number(UnitLevel('player'))
    local _, class = UnitClass('player')
    state.class = text(class)
    state.mapId = number(C_Map.GetBestMapForUnit('player'))
    if state.mapId then
        local position = C_Map.GetPlayerMapPosition(state.mapId, 'player')
        if public(position) and position then
            local x, y = position:GetXY()
            x, y = number(x), number(y)
            if x and y and x >= 0 and y >= 0 and (x > 0 or y > 0) then
                state.x, state.y = math.floor(x * 1000 + .5) / 10, math.floor(y * 1000 + .5) / 10
            end
        end
    end
    local guid = text(UnitGUID('target'))
    if guid then
        local kind, npcId = guid:match('^(%a+)%-[^-]+%-[^-]+%-[^-]+%-[^-]+%-(%d+)%-')
        if kind == 'Creature' or kind == 'Vehicle' then
            state.target = {id = tonumber(npcId), name = text(UnitName('target'))}
        end
    end
    local selected = number(C_QuestLog.GetSelectedQuest())
    local count = number(C_QuestLog.GetNumQuestLogEntries()) or 0
    local quests = {}
    for i = 1, count do
        local info = C_QuestLog.GetInfo(i)
        if public(info) and info and public(info.isHeader) and not info.isHeader then
            local id = number(info.questID)
            if id then
                local complete = C_QuestLog.IsComplete(id)
                local quest = {id = id, complete = public(complete) and complete == true or false}
                quests[#quests + 1] = quest
                if id == selected then
                    state.selectedQuest = {id = id, title = text(info.title), complete = quest.complete}
                    local objectives = C_QuestLog.GetQuestObjectives(id)
                    if public(objectives) and objectives then
                        local lines = {}
                        for _, objective in ipairs(objectives) do
                            if public(objective) then
                                local line = text(objective.text)
                                if line then lines[#lines + 1] = line end
                            end
                        end
                        if #lines > 0 then state.selectedQuest.objectives = lines end
                    end
                end
            end
        end
    end
    if #quests > 0 then state.quests = quests end
    if #W.json(state) > W.maxBody and state.selectedQuest then
        state.selectedQuest.objectives = nil
        state.truncated = true
    end
    while #W.json(state) > W.maxBody and state.quests and #state.quests > 0 do
        table.remove(state.quests)
        state.truncated = true
        if #state.quests == 0 then state.quests = nil end
    end
    return state
end

local function update()
    if not enabled or not IsLoggedIn() then frame:Hide(); return end
    frame:SetScale(1 / UIParent:GetEffectiveScale())
    local ok, state = pcall(snapshot)
    if not ok then state = {version = 1, sampledAt = time(), error = 'public API unavailable'} end
    sequence = (sequence + 1) % 4294967296
    local packetOK, packet = pcall(W.packet, state, sequence)
    if not packetOK then packet = W.packet({version = 1, sampledAt = time(), error = 'payload too large'}, sequence) end
    local colors = W.colors(packet)
    for i, texture in ipairs(textures) do
        local color = colors[i] or {0, 0, 0}
        texture:SetColorTexture(color[1] / 255, color[2] / 255, color[3] / 255, 1)
    end
    frame:Show()
end

SLASH_WHALEBRIDGE1 = '/whale'
SlashCmdList.WHALEBRIDGE = function(command)
    if command == 'off' then enabled = false; frame:Hide()
    elseif command == 'on' then enabled = true; update()
    else print('Whale Bridge: /whale on | /whale off. Non-combat quest/location context; keep the pixel panel visible.') end
end
C_Timer.NewTicker(1, update)
update()
